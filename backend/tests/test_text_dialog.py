"""Текстовый диалог: ровно те запросы, что шлёт frontend/js/text-dialog.js."""
import json
import time

import pytest

from app.core.utilits import r
from app.core.config import MODE_TTL
from app.database import async_session
from app.models import DialogHistory, Level
from conftest import new_session_id
from sqlalchemy import select


def send(client, headers, sid, message="Добрый день!", level="normal", mode="norm"):
    return client.post(f"/text/send/{sid}", json={"message": message, "level": level, "mode": mode},
                       headers=headers)


def history(client):
    async def fetch():
        async with async_session() as db:
            return (await db.execute(select(DialogHistory))).scalars().all()
    return client.portal.call(fetch)


def test_send_and_continue(client, user, fake_ai):
    sid = new_session_id()
    fake_ai.replies = ["Алло, да.", "Ну, допустим, слушаю."]
    res = send(client, user, sid)
    assert res.status_code == 200, res.text
    assert res.json() == {"response": "Алло, да.", "status": "success", "end_dialog": False}

    res = send(client, user, sid, message="Я звоню по поводу CRM")
    assert res.json()["response"] == "Ну, допустим, слушаю."
    # во второй запрос в LLM ушёл весь контекст: system + 3 реплики
    ctx = fake_ai.calls[-1]
    assert ctx[0]["role"] == "system"
    assert [m["role"] for m in ctx[1:]] == ["user", "assistant", "user"]


@pytest.mark.parametrize("level,marker", [("easy", "дружелюбный"), ("normal", "сомневайся"), ("hard", "скептически")])
def test_level_prompt_used(client, user, fake_ai, level, marker):
    send(client, user, new_session_id(), level=level)
    assert marker in fake_ai.calls[0][0]["content"]


def test_level_fixed_for_session(client, user, fake_ai):
    sid = new_session_id()
    send(client, user, sid, level="easy")
    send(client, user, sid, level="hard")  # попытка поменять сложность посреди диалога
    assert "дружелюбный" in fake_ai.calls[1][0]["content"]


@pytest.mark.parametrize("payload", [
    {"message": "hi", "level": "medium", "mode": "norm"},
    {"message": "hi", "level": "normal", "mode": "normal"},  # у mode средний вариант — norm
    {"message": "", "level": "normal", "mode": "norm"},
    {"message": "x" * 1001, "level": "normal", "mode": "norm"},
    {"level": "normal", "mode": "norm"},
])
def test_send_validation(client, user, fake_ai, payload):
    res = client.post(f"/text/send/{new_session_id()}", json=payload, headers=user)
    assert res.status_code == 422
    assert fake_ai.calls == []


def test_send_requires_auth(client, fake_ai):
    res = client.post(f"/text/send/{new_session_id()}", json={"message": "hi", "level": "easy", "mode": "easy"})
    assert res.status_code == 401


def test_goodbye_ends_dialog_and_saves_history(client, user, fake_ai):
    sid = new_session_id()
    fake_ai.replies = ["Алло.", "Нет, спасибо, нам не надо. До свидания!"]
    send(client, user, sid, level="hard", mode="hard")
    res = send(client, user, sid, message="Купите у нас")
    assert res.json() == {"response": "Нет, спасибо, нам не надо. До свидания!",
                          "status": "success", "end_dialog": True}

    rows = history(client)
    assert len(rows) == 1
    assert rows[0].level == Level.hard
    assert [m["role"] for m in rows[0].messages_list] == ["me", "client", "me", "client"]

    # сессия закрыта: повтор с тем же id не начинает новый диалог молча
    assert send(client, user, sid).status_code == 409
    # и закрыть её ещё раз нельзя
    assert client.delete(f"/text/close_session/{sid}", headers=user).status_code == 404


def test_timeout(client, user, fake_ai):
    sid = new_session_id()
    send(client, user, sid, mode="hard")
    # перематываем дедлайн в прошлое
    key = next(k for k in r.keys("full_dialog:*"))
    data = json.loads(r.get(key))
    assert abs(data["deadline"] - time.time() - MODE_TTL["hard"]) < 5
    data["deadline"] = time.time() - 1
    r.set(key, json.dumps(data))

    res = send(client, user, sid)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "timeout" and body["end_call"] is True
    assert len(fake_ai.calls) == 1  # в LLM после таймаута не ходили
    assert len(history(client)) == 1  # история сохранена даже при таймауте


def test_close_session_saves_history(client, user, fake_ai):
    sid = new_session_id()
    send(client, user, sid)
    res = client.delete(f"/text/close_session/{sid}", headers=user)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "success"
    rows = history(client)
    assert len(rows) == 1 and rows[0].level == Level.normal
    me = client.get("/reg/me", headers=user).json()
    assert rows[0].user_id == me["user_id"]
    # память диалога вычищена
    assert r.keys("chat:*") == []


def test_close_unknown_session(client, user):
    assert client.delete(f"/text/close_session/{new_session_id()}", headers=user).status_code == 404


def test_sessions_isolated_between_users(client, make_user, fake_ai):
    alice = make_user("alice", "alice@test.ru")
    bob = make_user("bob", "bob@test.ru")
    sid = new_session_id()
    send(client, alice, sid, message="секрет алисы")

    # Боб с тем же session_id не может закрыть сессию Алисы...
    assert client.delete(f"/text/close_session/{sid}", headers=bob).status_code == 404
    # ...и не видит её контекст
    send(client, bob, sid, message="привет")
    bob_ctx = json.dumps(fake_ai.calls[-1], ensure_ascii=False)
    assert "секрет алисы" not in bob_ctx
    # сессия Алисы жива
    assert client.delete(f"/text/close_session/{sid}", headers=alice).status_code == 200


def test_text_and_audio_sessions_independent(client, user, fake_ai):
    # раньше session_id подменялся на user_id, и два разных диалога пользователя смешивались
    s1, s2 = new_session_id(), new_session_id()
    send(client, user, s1, message="диалог один", level="easy")
    send(client, user, s2, message="диалог два", level="hard")
    ctx = json.dumps(fake_ai.calls[-1], ensure_ascii=False)
    assert "диалог один" not in ctx
    assert "скептически" in fake_ai.calls[-1][0]["content"]


def test_long_dialog_summarization(client, user, fake_ai):
    # раньше после 6 реплик суммаризация падала (KeyError 'replic' + openai без ключа) → 500
    sid = new_session_id()
    for i in range(6):
        res = send(client, user, sid, message=f"реплика {i}")
        assert res.status_code == 200, res.text
    summary_requests = [c for c in fake_ai.calls if "краткое содержание" in c[0]["content"]]
    assert summary_requests, "суммаризация должна была вызваться"
    last_ctx = fake_ai.calls[-1]
    assert len(last_ctx) <= 1 + 6


def test_llm_error_hides_traceback(client, user, fake_ai):
    fake_ai.replies = [RuntimeError("boom /secret/path.py")]
    res = send(client, user, new_session_id())
    assert res.status_code == 500
    detail = res.json()["detail"]
    assert "Traceback" not in detail and "/secret/path.py" not in detail

"""Голосовой диалог: ровно те запросы, что шлёт frontend/js/audio-dialog.js."""
import os
from urllib.parse import unquote

from app.core.config import cv
from conftest import new_session_id


def choose(client, headers, voice="woman"):
    return client.post("/dialog/choose_voice", json={"voice": voice}, headers=headers)


def turn(client, headers, sid, level="normal", mode="norm", audio=b"webm-bytes"):
    # api.js: multipart FormData — level, mode, file (turn.webm)
    return client.post(f"/dialog/process_turn/{sid}",
                       data={"level": level, "mode": mode},
                       files={"file": ("turn.webm", audio, "audio/webm")},
                       headers=headers)


def test_choose_voice(client, user):
    res = choose(client, user, "man")
    assert res.status_code == 200, res.text
    assert res.json() == {"status": "success", "choosen_voice": "man"}


def test_choose_voice_invalid(client, user):
    assert choose(client, user, "robot").status_code == 422


def test_choose_voice_requires_auth(client):
    assert client.post("/dialog/choose_voice", json={"voice": "man"}).status_code == 401


def test_turn_without_voice(client, user, fake_ai, fake_audio):
    res = turn(client, user, new_session_id())
    assert res.status_code == 400
    assert res.json()["detail"] == "голос не выбран"


def test_turn_returns_mp3(client, user, fake_ai, fake_audio):
    choose(client, user, "man")
    fake_ai.replies = ["Алло, да, слушаю."]
    res = turn(client, user, new_session_id())
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("audio/mpeg")
    assert res.content == b"ID3fake-mp3"
    assert unquote(res.headers["x-bot-response"]) == "Алло, да, слушаю."
    assert fake_audio["voices"] == [cv.DEFAULT_MAN]
    # распознанный текст ушёл в LLM
    assert fake_ai.calls[0][-1] == {"role": "user", "content": fake_audio["transcript"]["text"]}
    # временные файлы удалены (вход сразу, mp3-ответ после отправки)
    assert os.listdir("audio") == []


def test_turn_silence_does_not_end_call(client, user, fake_ai, fake_audio):
    choose(client, user)
    fake_audio["transcript"]["text"] = ""
    res = turn(client, user, new_session_id())
    assert res.status_code == 200
    assert res.json() == {"text_to_speak": "", "status": "silence", "end_call": False}
    assert fake_ai.calls == []


def test_turn_goodbye_ends_call(client, user, fake_ai, fake_audio):
    choose(client, user)
    sid = new_session_id()
    fake_ai.replies = ["Всего доброго."]
    res = turn(client, user, sid)
    assert res.json() == {"text_to_speak": "Всего доброго.", "status": "success", "end_call": True}
    assert turn(client, user, sid).status_code == 409


def test_turn_validation(client, user, fake_ai, fake_audio):
    choose(client, user)
    assert turn(client, user, new_session_id(), level="medium").status_code == 422
    assert turn(client, user, new_session_id(), mode="normal").status_code == 422
    res = client.post(f"/dialog/process_turn/{new_session_id()}", data={"level": "easy", "mode": "easy"},
                      headers=user)
    assert res.status_code == 422  # нет файла


def test_turn_too_large(client, user, fake_ai, fake_audio):
    choose(client, user)
    res = turn(client, user, new_session_id(), audio=b"0" * (10 * 1024 * 1024 + 1))
    assert res.status_code == 413


def test_close_audio_session(client, user, fake_ai, fake_audio):
    choose(client, user)
    sid = new_session_id()
    turn(client, user, sid)
    res = client.delete(f"/dialog/close_session/{sid}", headers=user)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "closed"
    assert client.delete(f"/dialog/close_session/{sid}", headers=user).status_code == 404

"""
Общая инфраструктура тестов.

- Переменные окружения выставляются ДО импорта приложения (Settings читается при импорте).
- БД: SQLite (aiosqlite) во временном файле.
- Redis: fakeredis с общим "сервером" для sync-клиентов (r, память диалога) и async-клиента (rate limiter).
- Внешние сервисы (OpenRouter, Whisper, edge-tts, SMTP) замоканы.
- Все запросы в тестах формируются так же, как во frontend/js/api.js. Это и есть контракт фронт ↔ бэк.
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="comsim_tests_")
os.environ.update({
    "OPENROUTER_KEY": "test-key",
    "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
    "SECRET_KEY": "test-secret",
    "JWT_ALGO": "HS256",
    "SMTP_HOST": "localhost",
    "SMTP_PORT": "25",
    "SMTP_USER": "noreply@test.local",  # SMTP "настроен" → почту нужно подтверждать кодом
    "SMTP_PASSWORD": "x",
    "REDIS_TTL": "600",
    "REDIS_URL": "redis://fake:6379",
    "DIALOG_LEN_BEFORE_SUM": "6",
})

import fakeredis  # noqa: E402
import redis  # noqa: E402
import redis.asyncio  # noqa: E402

FAKE_SERVER = fakeredis.FakeServer()
redis.Redis.from_url = classmethod(lambda cls, url=None, **kw: fakeredis.FakeRedis(server=FAKE_SERVER, **kw))
redis.asyncio.Redis.from_url = classmethod(
    lambda cls, url=None, **kw: fakeredis.aioredis.FakeRedis(server=FAKE_SERVER, **kw))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(_TMP)  # аудиофайлы (папка audio/) создаются во временной директории

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.dependencies import rate_limiter  # noqa: E402
from app.core.utilits import r  # noqa: E402
import app.routers.auth_routs as auth_routs  # noqa: E402
import app.routers.audio_rout as audio_rout  # noqa: E402
import app.routers.text_routs as text_routs  # noqa: E402
import app.repositories.dialog_repos as dialog_repos  # noqa: E402
import app.services.mail_service as mail_service  # noqa: E402


async def _no_rate_limit():
    return None


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_state(client):
    """Чистые БД и Redis перед каждым тестом; rate limiter по умолчанию выключен
    (иначе любой тест с >3 запросами упрётся в 429). Отдельный тест проверяет его работу."""
    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    client.portal.call(_reset)
    r.flushall()
    app.dependency_overrides[rate_limiter] = _no_rate_limit
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def sent_codes(monkeypatch):
    """Перехватывает письма с кодом: {email: последний код}."""
    codes = {}
    fake = lambda email, code: codes.__setitem__(email, code)
    monkeypatch.setattr(mail_service, "send_email_code", fake)
    return codes


class FakeAI:
    """Мок OpenRouter: отвечает репликами из очереди (или дефолтной), запоминает запросы."""
    def __init__(self):
        self.replies = []
        self.calls = []

    async def __call__(self, messages):
        self.calls.append(messages)
        if self.replies:
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return "Ну, слушаю вас."


@pytest.fixture
def fake_ai(monkeypatch):
    ai = FakeAI()
    monkeypatch.setattr(text_routs, "send_to_ai", ai)
    monkeypatch.setattr(audio_rout, "send_to_ai", ai)
    monkeypatch.setattr(dialog_repos, "send_to_ai", ai)
    return ai


@pytest.fixture
def fake_audio(monkeypatch):
    """Мок Whisper и edge-tts. transcript["text"] — что «сказал» пользователь."""
    transcript = {"text": "Здравствуйте, я из компании Ромашка"}
    voices_used = []

    def fake_transcribe(path):
        assert os.path.exists(path), "входной файл должен существовать в момент распознавания"
        return transcript["text"]

    async def fake_speak(text, key, voice):
        voices_used.append(voice)
        os.makedirs("audio", exist_ok=True)
        path = os.path.join("audio", f"response_{key.replace(':', '_')}.mp3")
        with open(path, "wb") as f:
            f.write(b"ID3fake-mp3")
        return path

    monkeypatch.setattr(audio_rout, "uploading_from_mp3", fake_transcribe)
    monkeypatch.setattr(audio_rout, "speak", fake_speak)
    return {"transcript": transcript, "voices": voices_used}


# ---------- хелперы в формате frontend/js/api.js ----------

def register(client, username="ivan", email="ivan@test.ru", password="secret123"):
    return client.post("/reg/regis", json={"username": username, "email": email, "password": password})


def login(client, email="ivan@test.ru", password="secret123"):
    # api.js: form-urlencoded, email в поле username
    return client.post("/reg/login", data={"username": email, "password": password})


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def make_user(client, sent_codes):
    """Полный путь фронта: регистрация → подтверждение кода → логин. Возвращает заголовки авторизации."""
    def _make(username="ivan", email="ivan@test.ru", password="secret123"):
        assert register(client, username, email, password).status_code == 200
        res = client.post("/reg/verify_email", json={"email": email, "code": sent_codes[email]})
        assert res.status_code == 200, res.text
        res = login(client, email, password)
        assert res.status_code == 200, res.text
        return auth_headers(res.json()["access_token"])
    return _make


@pytest.fixture
def user(make_user):
    return make_user()


def new_session_id():
    return str(uuid.uuid4())

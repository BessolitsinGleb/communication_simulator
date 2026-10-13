"""Защиты: rate limit, валидация session_id, CORS для фронта."""
from app.main import app
from app.dependencies import rate_limiter
from conftest import new_session_id


def test_rate_limiter(client, user):
    app.dependency_overrides.pop(rate_limiter, None)  # включаем настоящий лимитер (Lua-скрипт в Redis)
    codes = [client.post("/dialog/choose_voice", json={"voice": "man"}, headers=user).status_code
             for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]


def test_rate_limiter_on_login(client, user):
    app.dependency_overrides.pop(rate_limiter, None)
    codes = [client.post("/reg/login", data={"username": "ivan@test.ru", "password": "bad"}).status_code
             for _ in range(5)]
    assert 429 in codes


def test_session_id_must_be_uuid(client, user, fake_ai):
    for bad in ["123", "..%2F..%2Fetc", "not-a-uuid"]:
        res = client.post(f"/text/send/{bad}", json={"message": "hi", "level": "easy", "mode": "easy"},
                          headers=user)
        assert res.status_code in (404, 422), bad
    assert fake_ai.calls == []


def test_cors_preflight_from_file_origin(client):
    # страницы фронта открываются через file:// → Origin: null; или через локальный http-сервер
    for origin in ["null", "http://localhost:5500"]:
        res = client.options("/text/send/" + new_session_id(), headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        })
        assert res.status_code == 200, origin
        assert res.headers.get("access-control-allow-origin") in (origin, "*")


def test_cors_exposes_bot_response_header(client, user):
    res = client.get("/reg/me", headers={**user, "Origin": "http://localhost:5500"})
    assert "x-bot-response" in res.headers.get("access-control-expose-headers", "").lower()

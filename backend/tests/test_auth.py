"""Регистрация / подтверждение / логин / профиль: ровно те запросы, что шлёт frontend/js/auth.js и home.js."""
from datetime import datetime, timedelta

from jose import jwt

from app.core.config import s, VERIFY_MAX_ATTEMPTS
from conftest import register, login, auth_headers


def test_full_registration_flow(client, sent_codes):
    res = register(client)
    assert res.status_code == 200
    assert res.json() == {"message": "код отправлен на почту"}
    assert "ivan@test.ru" in sent_codes

    # до подтверждения логин запрещён
    assert login(client).status_code == 403

    res = client.post("/reg/verify_email", json={"email": "ivan@test.ru", "code": sent_codes["ivan@test.ru"]})
    assert res.status_code == 200, res.text

    res = login(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token_type"] == "bearer" and body["access_token"]

    res = client.get("/reg/me", headers=auth_headers(body["access_token"]))
    assert res.status_code == 200
    me = res.json()
    assert me["username"] == "ivan" and me["email"] == "ivan@test.ru" and isinstance(me["user_id"], int)
    assert "password" not in me


def test_login_json_body_is_rejected(client, user):
    # Старый формат фронта (JSON) бэкенд не принимает. Фикс сделан на стороне фронта (form-urlencoded).
    res = client.post("/reg/login", json={"email": "ivan@test.ru", "password": "secret123"})
    assert res.status_code == 422


def test_login_wrong_password(client, user):
    res = login(client, password="wrong-pass")
    assert res.status_code == 401
    assert res.json()["detail"] == "Неверный email или пароль"


def test_login_unknown_email(client):
    assert login(client, email="nobody@test.ru").status_code == 401


def test_duplicate_email(client, sent_codes):
    assert register(client).status_code == 200
    res = register(client, username="other")
    assert res.status_code == 400
    assert res.json()["detail"] == "Email уже существует"


def test_duplicate_username(client, sent_codes):
    assert register(client).status_code == 200
    res = register(client, email="other@test.ru")
    assert res.status_code == 400
    assert res.json()["detail"] == "Имя пользователя уже занято"


def test_register_validation(client, sent_codes):
    assert register(client, password="123").status_code == 422
    assert register(client, email="not-an-email").status_code == 422
    assert register(client, username="a").status_code == 422


def test_password_is_hashed(client, sent_codes):
    register(client)
    from app.models import Users
    from app.database import async_session
    from sqlalchemy import select

    async def fetch():
        async with async_session() as db:
            return (await db.execute(select(Users))).scalar_one()
    u = client.portal.call(fetch)
    assert u.password != "secret123" and u.password.startswith("$argon2")


def test_verify_wrong_code(client, sent_codes):
    register(client)
    res = client.post("/reg/verify_email", json={"email": "ivan@test.ru", "code": "000000"})
    assert res.status_code == 400
    assert res.json()["detail"] == "неверный код"


def test_verify_code_reuse_impossible(client, sent_codes):
    register(client)
    code = sent_codes["ivan@test.ru"]
    assert client.post("/reg/verify_email", json={"email": "ivan@test.ru", "code": code}).status_code == 200
    # код удалён после использования
    assert client.post("/reg/verify_email", json={"email": "ivan@test.ru", "code": code}).status_code == 400


def test_verify_bruteforce_limited(client, sent_codes):
    register(client)
    for _ in range(VERIFY_MAX_ATTEMPTS):
        client.post("/reg/verify_email", json={"email": "ivan@test.ru", "code": "000000"})
    # даже правильный код после исчерпания попыток не принимается
    res = client.post("/reg/verify_email", json={"email": "ivan@test.ru", "code": sent_codes["ivan@test.ru"]})
    assert res.status_code == 429


def test_verify_expired_code(client, sent_codes):
    register(client)
    from app.models import EmailCode
    from app.database import async_session
    from sqlalchemy import update

    async def expire():
        async with async_session() as db:
            await db.execute(update(EmailCode).values(expires_at=datetime.utcnow() - timedelta(minutes=1)))
            await db.commit()
    client.portal.call(expire)
    res = client.post("/reg/verify_email", json={"email": "ivan@test.ru", "code": sent_codes["ivan@test.ru"]})
    assert res.status_code == 400
    assert res.json()["detail"] == "Код истек"


def test_resend_code_flow(client, sent_codes):
    register(client)
    first = sent_codes["ivan@test.ru"]
    # api.js: JSON {email}
    res = client.post("/reg/resend_code", json={"email": "ivan@test.ru"})
    assert res.status_code == 200, res.text
    assert res.json() == {"message": "Код отправлен повторно"}
    second = sent_codes["ivan@test.ru"]
    # действует последний выданный код
    if first != second:
        assert client.post("/reg/verify_email",
                           json={"email": "ivan@test.ru", "code": first}).status_code == 400
    assert client.post("/reg/verify_email",
                       json={"email": "ivan@test.ru", "code": second}).status_code == 200


def test_resend_code_cooldown(client, sent_codes):
    register(client)
    assert client.post("/reg/resend_code", json={"email": "ivan@test.ru"}).status_code == 200
    assert client.post("/reg/resend_code", json={"email": "ivan@test.ru"}).status_code == 429


def test_resend_code_not_for_strangers(client, sent_codes):
    res = client.post("/reg/resend_code", json={"email": "victim@test.ru"})
    assert res.status_code == 400
    assert "victim@test.ru" not in sent_codes


def test_me_requires_token(client):
    assert client.get("/reg/me").status_code == 401


def test_me_garbage_token(client):
    assert client.get("/reg/me", headers=auth_headers("garbage")).status_code == 401


def test_me_forged_token(client, user):
    forged = jwt.encode({"sub": "1"}, "not-the-secret", algorithm="HS256")
    assert client.get("/reg/me", headers=auth_headers(forged)).status_code == 401


def test_me_expired_token(client, user):
    expired = jwt.encode({"sub": "1", "exp": datetime.utcnow() - timedelta(minutes=1)},
                         s.SECRET_KEY, algorithm=s.JWT_ALGO)
    assert client.get("/reg/me", headers=auth_headers(expired)).status_code == 401


def test_me_deleted_user(client):
    token = jwt.encode({"sub": "999", "exp": datetime.utcnow() + timedelta(minutes=5)},
                       s.SECRET_KEY, algorithm=s.JWT_ALGO)
    assert client.get("/reg/me", headers=auth_headers(token)).status_code == 401

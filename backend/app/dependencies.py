from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, Request
from .services.auth_service import AuthService
from .repositories.openrout_repos import choose_voice
from .database import get_db
from fastapi.security import OAuth2PasswordBearer
from .core.config import s
from .models import Users
from jose import jwt, JWTError
import time
import uuid

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/reg/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    # FIX: был голый `except:`. Он перехватывал и HTTPException, и вообще любые ошибки.
    # Теперь ловим только ошибки декодирования токена и неверный формат sub.
    try:
        payload = jwt.decode(token, s.SECRET_KEY, algorithms=[s.JWT_ALGO])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Недействительный токен",
                            headers={"WWW-Authenticate": "Bearer"})

    user = await db.get(Users, user_id)
    # FIX: если пользователь удалён, а токен ещё жив, возвращался None, и эндпоинты падали
    # с AttributeError (500). Теперь это 401.
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден",
                            headers={"WWW-Authenticate": "Bearer"})
    return user

async def get_auth_service(db: AsyncSession = Depends(get_db)):
    # FIX: AuthService вызывался с несуществующими аргументами (repo, security=...), а его __init__ принимает db.
    return AuthService(db)

async def rate_limiter(request: Request):
    redis_client = request.app.state.redis
    lua_script = request.app.state.rate_limit_script
    now_ms = int(time.time() * 1000)

    clear_before_ms = now_ms - 1000
    limit = 3

    user_key = f"rate_limit:{request.client.host}"

    result = await lua_script(
        keys=[user_key],
        args=[str(now_ms), str(clear_before_ms), str(limit)]
    )
    if result == 0:
        raise HTTPException(status_code=429, detail="Слишком много запросов, подождите секунду")

def get_session_id(session_id: str) -> str:
    # FIX: раньше эта зависимость декодировала JWT и возвращала user_id ВМЕСТО session_id из пути.
    # В итоге у пользователя была одна сессия на всё: текстовый и голосовой диалоги делили одни ключи Redis,
    # а session_id, который генерирует фронт, игнорировался. Теперь берём session_id из пути и проверяем,
    # что это UUID. Он используется в именах файлов, поэтому проверка заодно защищает от path traversal.
    try:
        return str(uuid.UUID(session_id))
    except ValueError:
        raise HTTPException(status_code=422, detail="session_id должен быть UUID")

def session_key(user: Users, session_id: str) -> str:
    # ADDED: Redis-ключи сессии привязаны к владельцу. Пользователь не может прочитать, продолжить или закрыть
    # чужую сессию, даже если узнает её UUID.
    return f"{user.user_id}:{session_id}"

async def get_voice(current_user: Users = Depends(get_current_user)):
    # FIX: убран лишний повторный SELECT пользователя: get_current_user уже вернул его из БД.
    if current_user.choosen_voice:
        return choose_voice(current_user.choosen_voice)
    else:
        raise HTTPException(400, detail="голос не выбран")

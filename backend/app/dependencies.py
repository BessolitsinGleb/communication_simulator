from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, Request
from .services.auth_service import AuthService
from .core import sequrity
from .repositories.openrout_repos import choose_voice
from .database import get_db
from .repositories.user_repos import UserRepo
from fastapi.security import OAuth2PasswordBearer
from .core.config import s
from .models import Users
from jose import jwt 
from sqlalchemy import select
import time

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/reg/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, s.SECRET_KEY, algorithms=[s.JWT_ALGO])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401)
    except:
        raise HTTPException(status_code=401)

    user = await db.get(Users, int(user_id))
    return user

async def get_auth_service(db: AsyncSession = Depends(get_db)):
    repo = UserRepo(db)
    return AuthService(repo, security= sequrity)

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
        raise HTTPException(status_code=429, detail="Too many requests")

async def get_session_id(token: str = Depends(oauth2_scheme),
                         db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, s.SECRET_KEY, algorithms=[s.JWT_ALGO])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401)
    except:
        raise HTTPException(status_code=401) 
    
    return user_id

async def get_voice(db: AsyncSession = Depends(get_db),
                    current_user: Users = Depends(get_current_user)):

    user = await db.execute(select(Users).where(Users.user_id == current_user.user_id))
    user = user.scalar_one_or_none()

    if user.choosen_voice:
        return choose_voice(user.choosen_voice)
    else:
        raise HTTPException(400, detail="голос не выбран")
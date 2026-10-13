from passlib.context import CryptContext
from datetime import timedelta, datetime
from .config import s
from jose import jwt, JWTError
import random
from ..database import async_session
from sqlalchemy import select
from ..models import Users

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hash: str) -> bool:
    return pwd_context.verify(password, hash)

def create_jwt_token(user_data: dict):
    if hasattr(user_data, "__dict__"):
        to_encode = dict(user_data.__dict__)
        to_encode.pop('_sa_instance_state', None)
    else:
        to_encode = user_data.copy()
    expire = datetime.utcnow() + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, s.SECRET_KEY, algorithm=s.JWT_ALGO)

def create_access_token(data: dict):
    return jwt.encode(data, s.SECRET_KEY, algorithm= s.JWT_ALGO)

def create_token(user):
    payload = {
        "sub": str(user.user_id),
        "email": user.email,
    }
    token = create_access_token(data= payload)
    return token 

async def decode_token(token: str):
    try:
        payload = jwt.decode(token, s.SECRET_KEY, algorithms=[s.JWT_ALGO])
        user_id = int(payload.get("sub"))

        async with async_session() as session:
            res = await session.execute(
                select(Users).where(Users.user_id == user_id)
            )
            user = res.scalar_one_or_none()
        return user
    except JWTError:
        return None

def generate_code():
    return str(random.randint(100000, 999999))
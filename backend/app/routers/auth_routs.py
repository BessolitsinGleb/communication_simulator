from fastapi import APIRouter, Depends, HTTPException, status
from ..schemas.auth_schema import UserReg, VerifyEmailschema, ResendCodeSchema
from ..services.auth_service import AuthService
from ..dependencies import get_current_user, rate_limiter
from ..core.utilits import r
from ..core.config import VERIFY_MAX_ATTEMPTS, VERIFY_ATTEMPTS_WINDOW_SEC
from ..database import get_db
from ..schemas.auth_schema import UserResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.sequrity import verify_password, create_jwt_token, generate_code
from sqlalchemy import select, delete
from ..models import Users, EmailCode
from datetime import datetime, timedelta
from ..services.mail_service import send_email_code

router = APIRouter(prefix="/reg", tags=["/reg"])

# FIX: на регистрацию, логин, подтверждение и повторную отправку кода добавлен rate_limiter.
# Раньше подбор пароля и кода, а также спам письмами ничем не ограничивались.
@router.post("/regis", dependencies=[Depends(rate_limiter)]) #, response_model= TokenResp)
async def register(
    user: UserReg,
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    await service.register(user)
    return {"message": "код отправлен на почту"}

# Логин принимает OAuth2-форму (username = email). Так работает кнопка Authorize в Swagger,
# поэтому формат на фронте (api.js) приведён к form-urlencoded, а не наоборот.
@router.post("/login", dependencies=[Depends(rate_limiter)])
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Users).where(Users.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.email_verified:
        raise HTTPException(
            status_code=403,
            detail="Подтвердите почту"
        )
    access_token = create_jwt_token({"sub": str(user.user_id)})
    return {
        "access_token": access_token, 
        "token_type": "bearer"
    }

@router.post("/verify_email", dependencies=[Depends(rate_limiter)])
async def verify_email(data: VerifyEmailschema, db: AsyncSession = Depends(get_db)):

    # FIX: код из 6 цифр можно было перебирать без ограничений. Теперь не больше VERIFY_MAX_ATTEMPTS
    # попыток на email за VERIFY_ATTEMPTS_WINDOW_SEC (счётчик сбрасывается при повторной отправке кода).
    attempts_key = f"verify_attempts:{data.email}"
    attempts = r.incr(attempts_key)
    if attempts == 1:
        r.expire(attempts_key, VERIFY_ATTEMPTS_WINDOW_SEC)
    if attempts > VERIFY_MAX_ATTEMPTS:
        raise HTTPException(429, "Слишком много попыток, запросите новый код")

    # FIX: без ORDER BY all_codes[-1] не гарантированно был последним выданным кодом.
    result = await db.execute(
        select(EmailCode).where(EmailCode.email == data.email).order_by(EmailCode.id)
    )

    all_codes = result.scalars().all()
    email_code = all_codes[-1] if all_codes else None

    if not email_code:
        raise HTTPException(400, "Код не найден")

    if email_code.code != data.code:                #DON'T FORGET PLS
        raise HTTPException(400, "неверный код")

    if email_code.expires_at < datetime.utcnow():
        raise HTTPException(400, "Код истек")

    result = await db.execute(
        select(Users).where(Users.email == data.email)
    )

    # FIX: scalar_one() падал с 500, если кода нет в users (например, пользователь удалён).
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(400, "Пользователь не найден")

    user.email_verified = True
    # FIX: использованные коды раньше не удалялись, и тем же кодом можно было подтверждать повторно.
    await db.execute(delete(EmailCode).where(EmailCode.email == data.email))

    await db.commit()
    r.delete(attempts_key)

    return {"message": "Почта подтверждена"}

@router.post("/resend_code", dependencies=[Depends(rate_limiter)])
async def resend_code(data: ResendCodeSchema, db: AsyncSession = Depends(get_db)):
    # FIX: email раньше ожидался в query-параметре, а фронт шлёт JSON {"email": ...} → 422.
    email = data.email

    # FIX: раньше код отправлялся на ЛЮБОЙ адрес без ограничений (сервер можно было использовать для спама).
    # Теперь письмо уходит только зарегистрированному пользователю с неподтверждённой почтой и не чаще раза в минуту.
    cooldown_key = f"resend_cooldown:{email}"
    if r.exists(cooldown_key):
        raise HTTPException(429, "Код можно запросить повторно через минуту")

    result = await db.execute(select(Users).where(Users.email == email))
    user = result.scalar_one_or_none()
    if not user or user.email_verified:
        raise HTTPException(400, "Пользователь не найден или почта уже подтверждена")

    r.set(cooldown_key, 1, ex=60)
    r.delete(f"verify_attempts:{email}")
    code = generate_code()

    email_code = EmailCode(
        email=email,
        code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(email_code)
    await db.commit()
    send_email_code(email, code)

    return {"message": "Код отправлен повторно"}

@router.get("/me", response_model= UserResponse)
async def me(current_user: Users = Depends(get_current_user)):
    # FIX: убран повторный SELECT. get_current_user уже загрузил пользователя и сам отдаёт 401, если его нет.
    return current_user
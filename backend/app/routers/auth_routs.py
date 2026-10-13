from fastapi import APIRouter, Depends, HTTPException, status
from ..schemas.auth_schema import UserReg, VerifyEmailschema
from ..services.auth_service import AuthService
from ..dependencies import get_current_user
from ..database import get_db
from ..schemas.auth_schema import UserResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.sequrity import verify_password, create_jwt_token, generate_code
from sqlalchemy import select
from ..models import Users, EmailCode
from datetime import datetime, timedelta
from ..services.mail_service import send_email_code

router = APIRouter(prefix="/reg", tags=["/reg"])

@router.post("/regis") #, response_model= TokenResp)
async def register(
    user: UserReg,
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    await service.register(user)
    return {"message": "код отправлен на почту"}

@router.post("/login")
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

@router.post("/verify_email")
async def verify_email(data: VerifyEmailschema, db: AsyncSession = Depends(get_db)):

    result = await db.execute(
        select(EmailCode).where(EmailCode.email == data.email)
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

    user = result.scalar_one()

    user.email_verified = True

    await db.commit()

    return {"message": "Почта подтверждена"}

@router.post("/resend_code")
async def resend_code(email: str, db: AsyncSession = Depends(get_db)):
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
async def me(current_user: Users = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = (
        select(Users)
        .where(Users.user_id == current_user.user_id))
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code= status.HTTP_401_UNAUTHORIZED,
            detail="user not found or token is invalid"
        )

    return user
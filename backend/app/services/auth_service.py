from ..repositories.user_repos import UserRepo
from ..services.mail_service import deliver_code
from ..core.sequrity import hash_password
from ..core.sequrity import generate_code
from ..core.config import s
from ..models import Users, EmailCode
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import delete


class AuthService:

    def __init__(self, db):
        self.db = db
        self.user_repo = UserRepo(db)

    async def register(self, data):

        user = await self.user_repo.get_by_email(data.email)

        # FIX: если почта зарегистрирована, но НЕ подтверждена, раньше возвращалось «Email уже существует».
        # Пользователь, у которого не дошло письмо или упала регистрация, застревал навсегда: войти нельзя
        # (403), зарегистрироваться заново тоже. Теперь неподтверждённая регистрация перезаписывается
        # и высылается новый код. Подтверждённые аккаунты по-прежнему защищены.
        if user and user.email_verified:
            raise HTTPException(400, "Email уже существует")

        # FIX: username в БД уникальный, но не проверялся. Повторное имя давало IntegrityError → 500.
        same_name = await self.user_repo.get_by_username(data.username)
        if same_name and same_name.user_id != (user.user_id if user else None):
            raise HTTPException(400, "Имя пользователя уже занято")

        hashed_password = hash_password(data.password)

        # FIX: раньше пользователь и код коммитились ДО отправки письма. Если SMTP падал, в БД оставался
        # неподтверждённый пользователь, а клиент получал 500. Теперь всё в одной транзакции:
        # коммит только после успешной отправки, при ошибке откат.
        if user:
            user.username = data.username
            user.password = hashed_password
            await self.db.execute(delete(EmailCode).where(EmailCode.email == data.email))
        else:
            user = Users(email=data.email, username=data.username, password=hashed_password,
                         email_verified=False)
            self.db.add(user)

        code = generate_code()
        self.db.add(EmailCode(email=data.email, code=code,
                              expires_at=datetime.utcnow() + timedelta(minutes=10)))

        if not s.SMTP_USER or not s.SMTP_PASSWORD:
            user.email_verified = True

        try:
            await self.db.flush()
            await deliver_code(data.email, code)
        except Exception:
            await self.db.rollback()
            raise

        await self.db.commit()
        await self.db.refresh(user)
        return user

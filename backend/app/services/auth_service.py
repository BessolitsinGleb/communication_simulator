from ..repositories.user_repos import UserRepo
from ..repositories.email_repos import EmailCodeRepository
from ..services.mail_service import send_email_code
from ..core.sequrity import hash_password
from ..core.sequrity import generate_code
from ..core.config import s
from fastapi import HTTPException


class AuthService:

    def __init__(self, db):
        self.user_repo = UserRepo(db)
        self.code_repo = EmailCodeRepository(db)

    async def register(self, data):

        user = await self.user_repo.get_by_email(data.email)

        if user:
            raise HTTPException(400, "Email уже существует")

        hashed_password = hash_password(data.password)

        new_user = await self.user_repo.create_user(
            email=data.email,
            username=data.username,
            password=hashed_password
        )

        code = generate_code()

        await self.code_repo.create_code(
            email=data.email,
            code=code
        )

        send_email_code(data.email, code)

        if not s.SMTP_USER or not s.SMTP_PASSWORD:
            new_user.email_verified = True
            await self.user_repo.db.commit()
            await self.user_repo.db.refresh(new_user)

        return new_user
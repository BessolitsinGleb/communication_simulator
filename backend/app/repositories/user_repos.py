from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Users

class UserRepo():
    def __init__(self, db: AsyncSession):
        self.db= db

    async def create_user(self, email, password, username):
        user = Users(
            email=email,
            password=password,
            username= username,
            email_verified = False
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_by_id(self, user_idd):
        result = await self.db.execute(
            select(Users).where(Users.user_id == user_idd)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email):
        result = await self.db.execute(
            select(Users).where(Users.email == email)
        )
        return result.scalar_one_or_none()

    # ADDED: нужен AuthService.register для проверки уникальности username.
    async def get_by_username(self, username):
        result = await self.db.execute(
            select(Users).where(Users.username == username)
        )
        return result.scalar_one_or_none()

    async def get_all(self):
        result = await self.db.execute(
            select(Users)
        )
        return result.scalars().all()      
from ..models import EmailCode
from datetime import datetime, timedelta


class EmailCodeRepository:

    def __init__(self, db):
        self.db = db

    async def create_code(self, email: str, code: str):

        email_code = EmailCode(
            email=email,
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )

        self.db.add(email_code)
        await self.db.commit()

        return email_code
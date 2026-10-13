from ..models import Users
from fastapi import HTTPException
from ..core.sequrity import create_jwt_token

class AuthLogin:    
    async def login(self, user_credentials):
        user = self.db.query(Users).filter(Users.email == user_credentials.email).first()
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        token_data = create_jwt_token(user) 

        token = self.security.create_access_token(data=token_data)
        return token
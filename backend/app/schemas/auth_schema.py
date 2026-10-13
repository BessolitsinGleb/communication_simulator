from pydantic import BaseModel, EmailStr

class UserReg(BaseModel):
    username: str
    email: EmailStr
    password: str

class Login(BaseModel):
    email: EmailStr
    password: str 

class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"

class VerifyEmailschema(BaseModel):
    email: str
    code: str

class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str

    model_config = {"from_attributes": True}
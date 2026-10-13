from pydantic import BaseModel, EmailStr, Field
from typing import Literal

class UserReg(BaseModel):
    # FIX: раньше никаких ограничений не было: можно было зарегистрироваться с пустым именем и паролем из 1 символа.
    username: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)

class Login(BaseModel):
    email: EmailStr
    password: str 

class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"

class VerifyEmailschema(BaseModel):
    email: str
    code: str

# ADDED: тело запроса /reg/resend_code. Раньше email ожидался в query-параметре,
# а фронт шлёт JSON {"email": ...}, из-за чего был 422.
class ResendCodeSchema(BaseModel):
    email: EmailStr

class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str

    model_config = {"from_attributes": True}


# ADDED: допустимые значения сложности и длительности. Раньше неизвестное значение
# доходило до choose_level/choose_ttl и роняло сервер (UnboundLocalError → 500), теперь это 422.
LevelLiteral = Literal["easy", "normal", "hard"]
ModeLiteral = Literal["easy", "norm", "hard"]

# ADDED: тело /dialog/choose_voice. Раньше voice ожидался в query, а фронт шлёт JSON {"voice": ...}.
class ChooseVoiceSchema(BaseModel):
    voice: Literal["man", "woman"]

# ADDED: тело /text/send. Раньше message/level/mode ожидались в query, а фронт шлёт JSON.
# Ограничение длины защищает от отправки огромных текстов в LLM за наш счёт.
class TextTurnSchema(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    level: LevelLiteral
    mode: ModeLiteral

from sqlalchemy.orm import Mapped, mapped_column
from pydantic import Field
from sqlalchemy import JSON
from .database import Base
from datetime import datetime
from enum import Enum
from typing import List

class Users(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str] = mapped_column(unique=True, nullable=True)
    email_verified: Mapped[bool] = mapped_column(default= False)
    password: Mapped[str] = mapped_column()
    choosen_voice: Mapped[str] = mapped_column()

class EmailCode(Base):
    __tablename__ = "email_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(nullable=False)
    code: Mapped[str] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column()

class Level(Enum):
    easy: str = "easy"
    normal: str = "normal"
    hard: str = "hard"

class DialogHistory(Base):
    __tablename__ = "dialod_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column()
    closed_at: Mapped[datetime] = mapped_column()
    level: Mapped[Level] = mapped_column(nullable=False)
    messages_list: Mapped[List[dict]] = mapped_column(
        type_=JSON, 
        default=list, 
        server_default="[]"
    )
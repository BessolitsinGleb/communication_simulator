"""
ADDED: общая логика жизненного цикла диалоговой сессии (текст и аудио).

Раньше этот код был скопирован в text_routs.py и audio_rout.py с одинаковыми багами:
  - remaining_ttl не определялся на первом ходе (NameError);
  - ключи level/full_dialog истекали одновременно, поэтому таймаут никогда не срабатывал:
    после истечения времени молча начинался новый диалог;
  - при завершении клиентом ("до свидания") и по таймауту история не сохранялась в БД;
  - level из Redis приходил как bytes и не подходил для Enum-колонки.

Схема хранения в Redis (key = "<user_id>:<session_id>"):
  full_dialog:{key} -> JSON {created_at, level, deadline, messages}. TTL = до дедлайна + DEADLINE_GRACE_SEC,
                       чтобы после окончания времени данные ещё были и их можно было сохранить в историю.
  closed:{key}      -> метка закрытой сессии. Повторные запросы с тем же session_id не открывают новый диалог.
"""
import json
import time
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import DEADLINE_GRACE_SEC, END_PHRASES
from ..core.utilits import r
from ..models import DialogHistory, Level
from ..repositories.dialog_repos import SummarizedConversationMemory
from ..repositories.openrout_repos import choose_ttl

ACTIVE, TIMEOUT, CLOSED = "active", "timeout", "closed"


def _dialog_key(key: str) -> str:
    return f"full_dialog:{key}"


def _closed_key(key: str) -> str:
    return f"closed:{key}"


def load_or_start(key: str, level: str, mode: str) -> tuple[str, dict]:
    """Возвращает (состояние, данные сессии). Если сессии ещё нет, создаёт её с дедлайном по mode."""
    if r.exists(_closed_key(key)):
        return CLOSED, {}

    raw = r.get(_dialog_key(key))
    if raw:
        data = json.loads(raw)
        if time.time() >= data["deadline"]:
            return TIMEOUT, data
        return ACTIVE, data

    data = {
        "created_at": datetime.utcnow().isoformat(),
        "level": level,
        "deadline": time.time() + choose_ttl(mode),
        "messages": [],
    }
    save(key, data)
    return ACTIVE, data


def save(key: str, data: dict) -> None:
    ttl = max(int(data["deadline"] - time.time()), 0) + DEADLINE_GRACE_SEC
    r.set(_dialog_key(key), json.dumps(data, ensure_ascii=False), ex=ttl)


def exists(key: str) -> bool:
    return bool(r.exists(_dialog_key(key)))


def is_goodbye(bot_response: str) -> bool:
    text = bot_response.lower()
    return any(phrase in text for phrase in END_PHRASES)


async def finalize(db: AsyncSession, user_id: int, key: str) -> bool:
    """Сохраняет историю в БД (если были сообщения) и чистит все данные сессии.
    Возвращает True, если история записана."""
    raw = r.get(_dialog_key(key))
    saved = False
    if raw:
        data = json.loads(raw)
        if data["messages"]:
            db.add(DialogHistory(
                user_id=user_id,
                created_at=datetime.fromisoformat(data["created_at"]),
                closed_at=datetime.utcnow(),
                level=Level(data["level"]),
                messages_list=data["messages"],
            ))
            await db.commit()
            saved = True

    SummarizedConversationMemory(user_id=key).clear_all_data()
    r.delete(_dialog_key(key))
    r.set(_closed_key(key), 1, ex=DEADLINE_GRACE_SEC)
    return saved

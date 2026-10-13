from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..dependencies import rate_limiter, get_current_user, get_session_id, session_key
from ..repositories.dialog_repos import SummarizedConversationMemory
from ..repositories.openrout_repos import send_to_ai, choose_level
from ..schemas.auth_schema import TextTurnSchema
from ..services import session_service as sessions
from ..models import Users
import traceback

# FIX: tags должен быть списком. Строка '/text' разбивалась Swagger'ом на отдельные символы-теги.
router = APIRouter(prefix='/text', tags=['/text'])

TIMEOUT_RESPONSE = {"text_to_speak": "Время вышло! Вы не успели завершить диалог.",
                    "status": "timeout", "end_call": True}

@router.post('/send/{session_id}', dependencies=[Depends(rate_limiter)])
async def send_message(body: TextTurnSchema,
                       session_id: str = Depends(get_session_id),
                       current_user: Users = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    # FIX: message/level/mode раньше ожидались в query-параметрах, а фронт шлёт JSON-тело → 422.
    # FIX: session_id раньше подменялся на user_id (см. dependencies.get_session_id).
    # FIX: логика TTL и сохранения вынесена в services/session_service.py: там исправлены NameError
    #      remaining_ttl, неработающий таймаут и потеря истории при завершении (подробности в модуле).
    key = session_key(current_user, session_id)

    state, session_data = sessions.load_or_start(key, body.level, body.mode)
    if state == sessions.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Сессия уже завершена, начните новый диалог")
    if state == sessions.TIMEOUT:
        await sessions.finalize(db, current_user.user_id, key)
        return TIMEOUT_RESPONSE

    # Уровень берём из сессии, а не из запроса: сложность нельзя поменять посреди диалога.
    memory = SummarizedConversationMemory(system_prompt=choose_level(session_data["level"]), user_id=key)

    try:
        await memory.add_message("user", body.message)
        session_data["messages"].append({"role": "me", "content": body.message})

        current_context = memory.get_messages_for_llm()
        bot_response = await send_to_ai(current_context)
        await memory.add_message("assistant", bot_response)
        session_data["messages"].append({"role": "client", "content": bot_response})
        sessions.save(key, session_data)

        if sessions.is_goodbye(bot_response):
            # FIX: раньше при завершении диалога ключи просто удалялись, и история в БД не попадала.
            await sessions.finalize(db, current_user.user_id, key)
            return {"response": bot_response, "status": "success", "end_dialog": True}

        return {"response": bot_response, "status": "success", "end_dialog": False}

    except Exception:
        # FIX: раньше в ответ клиенту отдавался полный traceback (утечка путей и внутренностей сервера).
        # Теперь traceback пишется только в лог сервера.
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера, попробуйте ещё раз")

@router.delete("/close_session/{session_id}")
async def close_session(session_id: str = Depends(get_session_id),
                        current_user: Users = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    # FIX: раньше в DialogHistory.user_id записывался session_id (по факту user_id из-за бага выше),
    # level приходил как bytes, а очистка памяти пряталась внутри условия if.
    key = session_key(current_user, session_id)
    if not sessions.exists(key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Активная сессия не найдена или уже была закрыта"
        )

    saved = await sessions.finalize(db, current_user.user_id, key)
    details = 'сессия успешно закрыта, история сохранена' if saved else 'сессия закрыта, сообщений не было'
    return {'status': 'success', 'details': details}

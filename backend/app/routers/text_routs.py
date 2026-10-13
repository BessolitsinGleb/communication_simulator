from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..dependencies import rate_limiter, get_current_user, get_session_id
from ..repositories.dialog_repos import SummarizedConversationMemory
from ..repositories.openrout_repos import send_to_ai, choose_level, choose_ttl
from ..models import Users, DialogHistory
import traceback, json
from datetime import datetime
from ..core.utilits import r
from ..core.config import s

router = APIRouter(prefix='/text', tags='/text')

@router.post('/send/{session_id}', dependencies=[Depends(rate_limiter)])
async def send_message(message: str,
                       level: str,
                       mode: str,
                       session_id: str = Depends(get_session_id),
                       current_user: Users = Depends(get_current_user)):
    
    sys_prompt = choose_level(level)
    current_ttl = choose_ttl(mode)
    memory = SummarizedConversationMemory(system_prompt=sys_prompt, user_id=session_id)

    redis_key = f"full_dialog:{session_id}"
    level_key = f"level:{session_id}" 

    get_level = r.get(level_key)
    session_raw = r.get(redis_key)

    if get_level and not session_raw:
            return {
                "text_to_speak": "Время вышло! Вы не успели завершить диалог.", 
                "status": "timeout", 
                "end_call": True
            }
    
    if session_raw and get_level:
        session_data = json.loads(session_raw)
            
        remaining_ttl = r.ttl(redis_key)
        if remaining_ttl <= 0:
            return {"text_to_speak": "Время вышло!", "status": "timeout", "end_call": True}
            
        current_ttl = remaining_ttl
    else:
        session_data = {
            "created_at": datetime.utcnow().isoformat(),
            "messages": []
        }
        r.setex(name=level_key, time=current_ttl, value=level)

    try:
        memory.add_message("user", message)
        session_data["messages"].append({"role": "me", "content": message})
        
        current_context = memory.get_messages_for_llm()
        bot_response = await send_to_ai(current_context)
        memory.add_message("assistant", bot_response)
        session_data["messages"].append({"role": "client", "content": bot_response})

        if "всего доброго" in bot_response.lower() or "до свидания" in bot_response.lower():
            memory.clear_all_data()
            r.delete(redis_key, level_key)
            return {"response": bot_response, "status": "success", "end_dialog": True}

        r.setex(redis_key, remaining_ttl, json.dumps(session_data, ensure_ascii=False))
        r.setex(level_key, remaining_ttl, level)
        return {"response": bot_response, "status": "success", "end_dialog": False}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка в эндпоинте: {str(e)}, traceback: {traceback.format_exc()}")

@router.delete("/close_session/{session_id}")
async def close_session(session_id: str = Depends(get_session_id),
                        current_user: Users = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    redis_key = f"full_dialog:{session_id}"
    level = r.get(f"level:{session_id}")
    memory = SummarizedConversationMemory(user_id=session_id)

    session_raw = r.get(redis_key)
    if not session_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Активная сессия не найдена или уже была закрыта"
        )
    session_data = json.loads(session_raw)

    if memory.clear_all_data() and (session_data["messages"]):
        new_archive_entry = DialogHistory(
                user_id=session_id,
                created_at=datetime.fromisoformat(session_data["created_at"]),
                closed_at=datetime.utcnow(),
                level=level,
                messages_list=session_data["messages"]
            )
        db.add(new_archive_entry)
        await db.commit()
        r.delete(redis_key)

        return {'status': 'success', 'details': 'сессия успешно закрыта, история сохранена'}
    return {"status": "Сессия не найдена или уже была удалена"}
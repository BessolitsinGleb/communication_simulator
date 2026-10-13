from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, status
from fastapi.responses import FileResponse
from ..repositories.openrout_repos import send_to_ai, uploading_from_mp3, get_file_path, speak, choose_level, choose_ttl
from ..repositories.dialog_repos import SummarizedConversationMemory
from ..dependencies import rate_limiter, get_session_id, get_current_user, get_voice
from ..core.config import UDLOADING_DIR
from ..core.utilits import r
import traceback, os, json
from urllib.parse import quote
from datetime import datetime
from ..models import Users, DialogHistory
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from ..database import get_db

router = APIRouter(prefix='/dialog', tags=['/dialog'])

@router.post("/process_turn/{session_id}", dependencies=[Depends(rate_limiter)])
async def process_turn(level: str,
                       mode: str,
                       session_id: str = Depends(get_session_id),
                       file: UploadFile = File(...),
                       current_user: Users = Depends(get_current_user)):
    sid = session_id
    sys_prompt = choose_level(level)
    current_ttl = choose_ttl(mode)
    voice = get_voice()
    memory = SummarizedConversationMemory(system_prompt=sys_prompt, user_id=sid)
    file_path = get_file_path(session_id)

    redis_key = f"full_dialog:{sid}"
    level_key = f"level:{sid}" 

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
        if not os.path.exists(UDLOADING_DIR):
            os.makedirs(UDLOADING_DIR)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        text_said = uploading_from_mp3(file_path)       
        if not text_said:
            return {"text_to_speak": "", "status": "silence", "end_call": False}

        memory.add_message("user", text_said)
        session_data["messages"].append({"role": "me", "content": text_said})

        current_context = memory.get_messages_for_llm()
        
        bot_response = await send_to_ai(current_context)
        memory.add_message("assistant", bot_response)
        session_data["messages"].append({"role": "client", "content": bot_response})
        
        if "всего доброго" in bot_response.lower() or "до свидания" in bot_response.lower():
            memory.clear_all_data()
            r.delete(redis_key, level_key)
            return {"text_to_speak": bot_response, "status": "success", "end_call": True}
            
        audio_path = await speak(bot_response, sid, voice)
        safe_bot_response = quote(bot_response)

        r.setex(redis_key, remaining_ttl, json.dumps(session_data, ensure_ascii=False))
        r.setex(level_key, remaining_ttl, level)
        return FileResponse(
            path=audio_path, 
            media_type="audio/mpeg", 
            filename=f"response_{sid}.mp3",
            headers={"X-Bot-Response": safe_bot_response} 
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500,
                            detail=f"Ошибка в эндпоинте: {str(e)}, traceback: {traceback.format_exc()}")
    
@router.delete("/close_session/{session_id}")
async def close_session(session_id: str = Depends(get_session_id),
                        current_user: Users = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    redis_key = f"full_dialog:{session_id}"
    level = r.get(f"level:{session_id}")
    memory = SummarizedConversationMemory(user_id=session_id)
    file_path = get_file_path(session_id)

    session_raw = r.get(redis_key)
    if not session_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Активная сессия не найдена или уже была закрыта"
        )
        
    session_data = json.loads(session_raw)

    if (os.path.exists(file_path)) and (memory.clear_all_data()) and (session_data["messages"]):
        os.remove(file_path)
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
        return {"status": "closed", "message": f"Сессия закрыта, файл удален, история сохранена"}
    
    return {"status": "Сессия не найдена или уже была удалена"}

@router.post('/choose_voice', dependencies=[Depends(rate_limiter)])
async def choose_voice(voice,
                       current_user: Users = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):

    smtp = await db.execute(select(Users).where(Users.user_id == current_user.user_id))
    user = smtp.scalar_one_or_none()

    if not user:
            raise HTTPException(
                status_code= status.HTTP_401_UNAUTHORIZED,
                detail="user not found or token is invalid"
            )
    update(user).values(choosen_voice = voice)

    await db.execute(user)
    await db.commit()

    return {'status': "success", 'choosen_voice': voice}
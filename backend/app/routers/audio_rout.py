from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from ..repositories.openrout_repos import send_to_ai, uploading_from_mp3, get_file_path, speak, choose_level
from ..repositories.dialog_repos import SummarizedConversationMemory
from ..dependencies import rate_limiter, get_session_id, get_current_user, get_voice, session_key
from ..core.config import UDLOADING_DIR
from ..schemas.auth_schema import ChooseVoiceSchema, LevelLiteral, ModeLiteral
from ..services import session_service as sessions
import traceback, os
from urllib.parse import quote
from ..models import Users
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db

router = APIRouter(prefix='/dialog', tags=['/dialog'])

TIMEOUT_RESPONSE = {"text_to_speak": "Время вышло! Вы не успели завершить диалог.",
                    "status": "timeout", "end_call": True}

# ADDED: ограничение размера загружаемой записи (10 МБ ≈ несколько минут речи). Без него можно было
# забить диск и память сервера одним запросом.
MAX_AUDIO_BYTES = 10 * 1024 * 1024

def _remove_file(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)

@router.post("/process_turn/{session_id}", dependencies=[Depends(rate_limiter)])
async def process_turn(level: LevelLiteral = Form(...),
                       mode: ModeLiteral = Form(...),
                       session_id: str = Depends(get_session_id),
                       file: UploadFile = File(...),
                       current_user: Users = Depends(get_current_user),
                       voice: str = Depends(get_voice),
                       db: AsyncSession = Depends(get_db)):
    # FIX: level/mode раньше ожидались в query, а фронт кладёт их в multipart FormData → 422.
    # FIX: voice раньше получался вызовом get_voice() напрямую. Это корутина без await и без зависимостей,
    #      поэтому голос никогда не определялся. Теперь get_voice подключается через Depends.
    # FIX: session_id подменялся на user_id; логика TTL/таймаута/сохранения вынесена в session_service.
    key = session_key(current_user, session_id)

    state, session_data = sessions.load_or_start(key, level, mode)
    if state == sessions.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Сессия уже завершена, начните новый звонок")
    if state == sessions.TIMEOUT:
        await sessions.finalize(db, current_user.user_id, key)
        return TIMEOUT_RESPONSE

    memory = SummarizedConversationMemory(system_prompt=choose_level(session_data["level"]), user_id=key)
    file_path = get_file_path(key)

    try:
        content = await file.read()
        if len(content) > MAX_AUDIO_BYTES:
            raise HTTPException(413, detail="Слишком длинная запись")

        if not os.path.exists(UDLOADING_DIR):
            os.makedirs(UDLOADING_DIR)
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        try:
            # FIX: whisper.transcribe синхронный и тяжёлый. Вызов прямо в async-эндпоинте блокировал
            # event loop, и сервер переставал отвечать всем пользователям на время распознавания.
            text_said = await run_in_threadpool(uploading_from_mp3, file_path)
        finally:
            # FIX: входная запись раньше оставалась на диске до close_session (или навсегда).
            _remove_file(file_path)

        if not text_said:
            return {"text_to_speak": "", "status": "silence", "end_call": False}

        await memory.add_message("user", text_said)
        session_data["messages"].append({"role": "me", "content": text_said})

        current_context = memory.get_messages_for_llm()

        bot_response = await send_to_ai(current_context)
        await memory.add_message("assistant", bot_response)
        session_data["messages"].append({"role": "client", "content": bot_response})
        sessions.save(key, session_data)

        if sessions.is_goodbye(bot_response):
            # FIX: раньше при завершении история в БД не сохранялась.
            await sessions.finalize(db, current_user.user_id, key)
            return {"text_to_speak": bot_response, "status": "success", "end_call": True}

        audio_path = await speak(bot_response, key, voice)
        safe_bot_response = quote(bot_response)

        return FileResponse(
            path=audio_path,
            media_type="audio/mpeg",
            filename=f"response_{session_id}.mp3",
            headers={"X-Bot-Response": safe_bot_response},
            # FIX: mp3-ответы раньше копились на диске. Теперь файл удаляется после отправки клиенту.
            background=BackgroundTask(_remove_file, audio_path),
        )

    except HTTPException:
        raise
    except Exception:
        # FIX: traceback больше не отдаётся клиенту, только пишется в лог.
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера, попробуйте ещё раз")

@router.delete("/close_session/{session_id}")
async def close_session(session_id: str = Depends(get_session_id),
                        current_user: Users = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    # FIX: раньше сессия считалась закрытой, только если на диске оставался файл записи. Он один на всех
    # пользователей, поэтому история часто не сохранялась. Ещё level приходил как bytes, а user_id = session_id.
    key = session_key(current_user, session_id)
    if not sessions.exists(key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Активная сессия не найдена или уже была закрыта"
        )

    _remove_file(get_file_path(key))
    saved = await sessions.finalize(db, current_user.user_id, key)
    message = "Сессия закрыта, история сохранена" if saved else "Сессия закрыта, сообщений не было"
    return {"status": "closed", "message": message}

@router.post('/choose_voice', dependencies=[Depends(rate_limiter)])
async def choose_voice(body: ChooseVoiceSchema,
                       current_user: Users = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    # FIX: voice раньше ожидался в query, а фронт шлёт JSON {"voice": "man"|"woman"} → 422.
    #      Теперь значение ещё и валидируется: раньше можно было сохранить любую строку и сломать process_turn.
    # FIX: `update(user).values(...)` создавал выражение и выбрасывал его, а `db.execute(user)` с ORM-объектом
    #      падал. Голос никогда не сохранялся. Теперь просто меняем атрибут и коммитим.
    #      current_user загружен в той же сессии БД (FastAPI кэширует get_db в рамках запроса).
    current_user.choosen_voice = body.voice
    await db.commit()

    return {'status': "success", 'choosen_voice': body.voice}

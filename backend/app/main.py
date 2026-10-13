from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .routers.audio_rout import router as dialog_router
from.routers.auth_routs import router as auth_router
from.routers.text_routs import router as text_router
import uvicorn
from .database import engine, Base
from .core.config import s, SLIDING_WINDOW_LUA
from redis.asyncio import Redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = Redis.from_url(s.REDIS_URL, decode_responses=True)
    
    app.state.redis = redis_client
    app.state.rate_limit_script = redis_client.register_script(SLIDING_WINDOW_LUA)

    # FIX: создание таблиц перенесено сюда из @app.on_event("startup"). Когда у FastAPI задан lifespan,
    # обработчики on_event("startup") НЕ вызываются, поэтому таблицы в БД не создавались.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield  
    await redis_client.close()

app = FastAPI(title='comsim', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # FIX: без expose_headers браузер не даёт JS прочитать кастомный заголовок X-Bot-Response
    # (текст реплики бота в аудиодиалоге), и фронт не мог показать, что сказал собеседник.
    expose_headers=["X-Bot-Response"],
)
app.include_router(auth_router)
app.include_router(dialog_router)
app.include_router(text_router)


"""
Хранеие данных для диалога:

    2. Добавить автозначение сессии(уникальное) +-
    3. Добавить jwt-token в эндпоинты +-
    5. Настроить бд/зависимости +-

Расширить интерфейс:

    1. Написать фронтенд на фреймворке(vue/react)
    4. Добавить разные голоса +-
    5. Сохранение историю диалогов в бд +-
    7. !!Добавить текстовую версию!! +-
    10. добавить ограничение диалога по времени для сложности типо +-
    11. добавить логику победы/проигрыша в диалоге по фразам бота
    
Корректность работы:
    1. Удостовериться в асинхронной работе опенроутера(с разных аккаунтов 
                                                       одновременно отправка запроса)
    2. Проверять с нагрузками
    3. Насторить логи

Optional:
    3. Добавить вкладку-обучение для разговора с клиентом
    6. Добавить соревнования(позже)
    8. Добавить опрос при регистрации для определения уровня юзера
    9. Карьерная дорога / лор
"""
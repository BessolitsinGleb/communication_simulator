from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    OPENROUTER_KEY: str
    DATABASE_URL: str
    SECRET_KEY: str
    JWT_ALGO: str = "HS256" 
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str 
    SMTP_PASSWORD: str 
    REDIS_TTL: int
    REDIS_URL: str
    DIALOG_LEN_BEFORE_SUM: int = 6

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

s = Settings()
UDLOADING_DIR: str = "audio"
SLIDING_WINDOW_LUA: str = "\
        local key = KEYS[1]\
        local now = tonumber(ARGV[1])\
        local clear_before = tonumber(ARGV[2])\
        local limit = tonumber(ARGV[3])\
        redis.call('zremrangebyscore', key, 0, clear_before)\
        local current_requests = redis.call('zcard', key)\
        if current_requests < limit then\
            redis.call('zadd', key, now, now)\
            redis.call('expire', key, 2)\
            return 1\
        else\
            return 0\
        end"

class DifficultyLevel:

    EASY_PROMPT: str = 'qwerty'

    NORMAL_PROMPT: str = "Ты — потенциальный клиент, которому по телефону звонит менеджер по продажам. Твой профиль, сфера деятельности и отношение к продукту уже заданы в настройках или первом системном описании. Ты об этом знаешь, но вслух свою роль НЕ называешь.\
                        ГЛАВНЫЕ ПРАВИЛА ДЛЯ ГОЛОСОВОЙ ОЗВУЧКИ (TTS):\
                        1. Пиши исключительно живым разговорным языком для последующей озвучки голосом.\
                        2. СТРОГО ЗАПРЕЩЕНЫ: списки, буллиты, кавычки, звездочки (*), дефисы и любая текстовая разметка.\
                        3. Используй короткие, простые предложения.\
                        4. Добавляй маркеры живой речи: 'ну', 'так', 'слушайте', 'эм', 'секунду', 'ладно', 'угу'.\
                        5. Длина одного ответа — строго от 1 до 3 предложений. Не затягивай реплики.\
                        ПОВЕДЕНИЕ В НАЧАЛЕ И ХОДЕ ДИАЛОГА:\
                        - Твоя самая первая реплика — это обычное, короткое приветствие человека, который поднял трубку с незнакомого номера. Например: 'Алло, да' или 'Да, добрый день, слушаю'. \
                        - Ты НЕ рассказываешь, кто ты, где работаешь и какая у тебя проблема, пока продавец сам об этом не спросит или не назовет причину звонка.\
                        - Веди себя естественно: сомневайся, задавай встречные вопросы, защищай свои границы, но реагируй адекватно на сильные аргументы."

    HARD_PROMPT: str = "qwer67io"

dl = DifficultyLevel

class ChooseVoice:

    DEFAULT_WOMAN: str = "ru-RU-SvetlanaNeural"
    DEFAULT_MAN: str = "ru-RU-DmitryNeural"

cv = ChooseVoice
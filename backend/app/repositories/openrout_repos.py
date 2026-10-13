from ..core.config import s, dl, cv, MODE_TTL
import httpx, os, edge_tts
from ..core.config import UDLOADING_DIR

async def send_to_ai(messages_list: list):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {s.OPENROUTER_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek/deepseek-chat",
                "messages": messages_list
            },
            timeout=30.0
        )

        if response.status_code != 200:
            print(f"!!! Ошибка OpenRouter: {response.status_code} - {response.text}")
            response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"]

# FIX: раньше модель Whisper (~140 МБ) загружалась прямо при импорте модуля. Это замедляло каждый старт
# приложения и не давало импортировать код без whisper/torch (например, в тестах).
# Теперь модель загружается один раз при первом распознавании.
_whisper_model = None

def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model("base")
    return _whisper_model

def uploading_from_mp3(file_path: str) -> str:
    # Синхронная и тяжёлая функция: вызывать через run_in_threadpool, чтобы не блокировать event loop.
    if not os.path.exists(file_path):
        return ""

    result = _get_whisper_model().transcribe(file_path, language="ru")
    return result["text"].strip()

def get_file_path(session_key: str) -> str:
    # FIX: раньше возвращался один общий путь 'audio/voice_record.mp3' для ВСЕХ пользователей. При одновременных
    # звонках записи перезаписывали друг друга, и один пользователь мог получить расшифровку чужой речи.
    # Теперь у каждой сессии свой файл. Расширение не mp3, потому что браузер присылает webm/ogg/mp4,
    # а whisper (через ffmpeg) определяет формат по содержимому.
    safe_name = session_key.replace(":", "_")
    return os.path.join(UDLOADING_DIR, f"input_{safe_name}.audio")

async def speak(text: str, session_key: str, voice: str):
    # FIX: сюда уже приходит готовое имя голоса edge-tts (get_voice → choose_voice). Повторный вызов
    # choose_voice("ru-RU-...") не находил совпадений и падал с UnboundLocalError.
    if not os.path.exists(UDLOADING_DIR):
        os.makedirs(UDLOADING_DIR)

    safe_name = session_key.replace(":", "_")
    output_file = os.path.join(UDLOADING_DIR, f"response_{safe_name}.mp3")

    # Генерация аудио
    communicate = edge_tts.Communicate(text, voice)

    # КРИТИЧНО: Здесь обязательно должен быть await!
    await communicate.save(output_file)

    return output_file

# FIX: в choose_level / choose_voice / choose_ttl при неизвестном значении переменная оставалась
# неопределённой (UnboundLocalError → 500), а choose_ttl вообще не возвращала значение (None).
# Валидные значения теперь проверяются схемами (422), а здесь лежат простые словари.
_LEVEL_PROMPTS = {"easy": dl.EASY_PROMPT, "normal": dl.NORMAL_PROMPT, "hard": dl.HARD_PROMPT}
_VOICES = {"man": cv.DEFAULT_MAN, "woman": cv.DEFAULT_WOMAN}

def choose_level(level: str) -> str:
    return _LEVEL_PROMPTS[level]

def choose_voice(voice) -> str:
    return _VOICES[voice]

def choose_ttl(mode: str) -> int:
    return MODE_TTL[mode]

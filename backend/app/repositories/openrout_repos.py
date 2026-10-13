from ..core.config import s, dl, cv
import httpx, whisper, os, edge_tts
from ..core.config import UDLOADING_DIR
from fastapi import Depends

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

model = whisper.load_model("base")
def uploading_from_mp3(file_path: str) -> str:
    if not os.path.exists(file_path):
        return ""
    
    result = model.transcribe(file_path, language="ru")
    return result["text"].strip()

def get_file_path(session_id: str) -> str:
    return 'audio/voice_record.mp3'

async def speak(text: str, session_id: str, voice: str):
    
    VOICE = choose_voice(voice)
    if not os.path.exists(UDLOADING_DIR):
        os.makedirs(UDLOADING_DIR)
    
    output_file = os.path.join(UDLOADING_DIR, f"response_{session_id}.mp3")
    
    # Генерация аудио
    communicate = edge_tts.Communicate(text, VOICE)
    
    # КРИТИЧНО: Здесь обязательно должен быть await!
    await communicate.save(output_file) 
    
    return output_file

def choose_level(level: str) -> str:

    if level == 'easy':
        system_prompt = dl.EASY_PROMPT
    if level == 'normal':
        system_prompt = dl.NORMAL_PROMPT
    if level == 'hard':
        system_prompt = dl.HARD_PROMPT
    return system_prompt

def choose_voice(voice) -> str:

    if voice == "man":
        cur_voice = cv.DEFAULT_MAN
    if voice == "woman":
        cur_voice = cv.DEFAULT_WOMAN
    return cur_voice

def choose_ttl(mode: str) -> int:
    if mode == 'easy':
        current_ttl = 300
    if mode == 'norm':
        current_ttl = 180
    if mode == 'hard':
        current_ttl = 60
import smtplib
import traceback
from email.mime.text import MIMEText
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from ..core.config import s

# ADDED: таймаут SMTP-соединения. Раньше его не было: если SMTP-сервер недоступен (например, провайдер
# блокирует smtp.gmail.com), smtplib висел до обрыва соединения.
SMTP_TIMEOUT_SEC = 10

def send_email_code(email: str, code: str):
    if not s.SMTP_USER or not s.SMTP_PASSWORD:
        print("SMTP credentials are not configured, skipping email send")
        return

    msg = MIMEText(f"Ваш код подтверждения: {code}")
    msg["Subject"] = "Подтверждение почты"
    msg["From"] = s.SMTP_USER
    msg["To"] = email

    with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=SMTP_TIMEOUT_SEC) as server:
        server.starttls()
        server.login(s.SMTP_USER, s.SMTP_PASSWORD)
        server.send_message(msg)

async def deliver_code(email: str, code: str) -> None:
    """ADDED: безопасная отправка кода из async-эндпоинтов.

    FIX (баг «замерзания» на регистрации):
      - send_email_code синхронный. Вызов прямо в async-эндпоинте блокировал event loop, и пока висело
        SMTP-соединение, сервер не отвечал НИКОМУ. Теперь вызов идёт в пуле потоков.
      - любая ошибка SMTP раньше превращалась в голый 500 без CORS-заголовков, и браузер показывал
        «не удалось связаться с сервером». Теперь это 503 с понятным текстом (вызывающий код откатывает БД).
      - EMAIL_FALLBACK_TO_LOG=true (для разработки): если письмо не ушло, код пишется в лог сервера
        (docker logs comsim_backend) и регистрация продолжается.
    """
    try:
        await run_in_threadpool(send_email_code, email, code)
    except Exception:
        traceback.print_exc()
        if s.EMAIL_FALLBACK_TO_LOG:
            print(f"[EMAIL_FALLBACK_TO_LOG] письмо не отправлено, код подтверждения для {email}: {code}", flush=True)
            return
        raise HTTPException(503, "Не удалось отправить письмо с кодом. Попробуйте позже")

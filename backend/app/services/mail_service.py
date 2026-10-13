import smtplib
from email.mime.text import MIMEText
from ..core.config import s

def send_email_code(email: str, code: str):
    if not s.SMTP_USER or not s.SMTP_PASSWORD:
        print("SMTP credentials are not configured, skipping email send")
        return

    msg = MIMEText(f"Ваш код подтверждения: {code}")
    msg["Subject"] = "Подтверждение почты"
    msg["From"] = s.SMTP_USER
    msg["To"] = email

    with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT) as server:
        server.starttls()
        server.login(s.SMTP_USER, s.SMTP_PASSWORD)
        server.send_message(msg)
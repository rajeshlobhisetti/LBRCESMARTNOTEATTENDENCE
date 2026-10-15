import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Settings:
    # MongoDB
    MONGODB_URI: str = os.getenv(
        "MONGODB_URI",
        "mongodb+srv://surya:surya@cluster0.vyreenm.mongodb.net/attendence?retryWrites=true&w=majority"
    )
    DB_NAME: str = os.getenv("DB_NAME", "attendence")

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "8523038213:AAErnH_G_r4mnCH1wfgBe-JTTFNjDgdjwXs"
    )
    TELEGRAM_BOT_USERNAME: str = os.getenv("TELEGRAM_BOT_USERNAME", "LBRCEattendancebot")

    # LBRCE ERP
    ERP_BASE_URL: str = os.getenv("ERP_BASE_URL", "https://erp.lbrce.ac.in")

    # Security / Admin
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-jwt-key-lbrce-attendance-2025-secure-token")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin@lbrce2025")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@lbrce.ac.in")

    # Schedule Times (24-hour format)
    MORNING_CRON_HOUR: int = int(os.getenv("MORNING_CRON_HOUR", "8"))
    MORNING_CRON_MINUTE: int = int(os.getenv("MORNING_CRON_MINUTE", "0"))
    NIGHT_CRON_HOUR: int = int(os.getenv("NIGHT_CRON_HOUR", "20"))
    NIGHT_CRON_MINUTE: int = int(os.getenv("NIGHT_CRON_MINUTE", "0"))

    # Email / SMTP
    SMTP_ENABLED: bool = os.getenv("SMTP_ENABLED", "true").lower() in ("true", "1", "yes")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "no-reply@lbrce-attendance.edu")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "LBRCE Attendance Alerts")

settings = Settings()

import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.models import StudentRegisterRequest, VerifyERPRequest
from app.database import db
from app.config import settings
from app.email_service import send_registration_success_email
from app.telegram_bot import telegram_service
from app.scraper import verify_credentials_quick

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "bot_username": settings.TELEGRAM_BOT_USERNAME,
            "bot_token_preview": settings.TELEGRAM_BOT_TOKEN[:10] + "..."
        }
    )

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {
            "request": request,
            "bot_username": settings.TELEGRAM_BOT_USERNAME,
            "bot_token_preview": settings.TELEGRAM_BOT_TOKEN[:10] + "..."
        }
    )

@router.get("/register/success", response_class=HTMLResponse)
async def register_success_page(request: Request, roll_no: str = "", name: str = ""):
    return templates.TemplateResponse(
        "register_success.html",
        {
            "request": request,
            "roll_no": roll_no,
            "name": name,
            "bot_username": settings.TELEGRAM_BOT_USERNAME
        }
    )

@router.post("/api/verify-erp")
async def verify_erp_login(payload: VerifyERPRequest):
    """
    Optional live check allowing the student to confirm their ERP credentials.
    """
    roll = payload.roll_no.strip().upper()
    valid, message = verify_credentials_quick(roll, payload.erp_password)
    return {"valid": valid, "message": message}

@router.post("/api/register")
async def register_student(payload: StudentRegisterRequest, background_tasks: BackgroundTasks):
    """
    Registers a student and dispatches confirmation email & Telegram welcome message.
    """
    roll_no = payload.roll_no.strip().upper()
    name = payload.name.strip()
    email = payload.email.strip().lower()
    telegram_chat_id = payload.telegram_chat_id.strip()
    erp_password = payload.erp_password.strip()

    # Check if student already exists
    existing = db.students.find_one({"roll_no": roll_no})

    student_data = {
        "name": name,
        "roll_no": roll_no,
        "email": email,
        "telegram_chat_id": telegram_chat_id,
        "erp_password": erp_password,
        "is_active": True,
        "updated_at": datetime.utcnow()
    }

    if existing:
        db.students.update_one({"roll_no": roll_no}, {"$set": student_data})
        action = "updated"
    else:
        student_data["created_at"] = datetime.utcnow()
        student_data["last_scraped_at"] = None
        student_data["last_overall_percentage"] = None
        student_data["last_attendance_data"] = []
        student_data["last_error"] = None
        db.students.insert_one(student_data)
        action = "created"

    logger.info(f"Student {roll_no} ({name}) {action} successfully.")

    # Background tasks for notifications
    # 1. Send confirmation email
    background_tasks.add_task(
        send_registration_success_email,
        name=name,
        roll_no=roll_no,
        to_email=email,
        telegram_chat_id=telegram_chat_id
    )

    # 2. Send instant Telegram welcome message
    welcome_text = (
        f"🎉 *Registration Successful!*\n\n"
        f"Hello *{name}* (`{roll_no}`),\n"
        f"Your registration for LBRCE Attendance Alerts is active!\n\n"
        f"⏰ *Automated Schedule:*\n"
        f"• Morning: *8:00 AM*\n"
        f"• Night: *8:00 PM*\n\n"
        f"💡 *Tip:* Send `/attendance` at any time to receive an on-demand report."
    )
    background_tasks.add_task(
        telegram_service.send_message,
        chat_id=telegram_chat_id,
        text=welcome_text
    )

    return {
        "success": True,
        "message": f"Successfully {action} registration for {name} ({roll_no})!",
        "roll_no": roll_no,
        "name": name
    }

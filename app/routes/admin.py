import logging
from datetime import datetime
from fastapi import APIRouter, Request, Response, HTTPException, status, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.models import AdminLoginRequest, StudentRegisterRequest, StudentUpdateRequest
from app.database import db
from app.config import settings
from app.auth import verify_password, get_password_hash, create_access_token, get_current_admin
from app.scheduler import process_single_student, run_batch_attendance

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/admin", response_class=HTMLResponse)
async def admin_root(request: Request):
    token = request.cookies.get("access_token")
    if token:
        try:
            return RedirectResponse(url="/admin/dashboard", status_code=302)
        except Exception:
            pass
    return RedirectResponse(url="/admin/login", status_code=302)

@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@router.post("/api/admin/login")
async def api_admin_login(payload: AdminLoginRequest, response: Response):
    admin = db.admins.find_one({"username": payload.username})
    if not admin or not verify_password(payload.password, admin.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin username or password"
        )

    token = create_access_token({"sub": admin["username"], "role": admin.get("role", "admin")})
    # Set HTTP-only secure cookie
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 24 * 7,
        samesite="lax"
    )
    return {"success": True, "token": token, "username": admin["username"]}

@router.post("/api/admin/logout")
async def api_admin_logout(response: Response):
    response.delete_cookie("access_token")
    return {"success": True, "message": "Logged out successfully"}

@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request):
    try:
        current_admin = get_current_admin(request)
    except HTTPException:
        return RedirectResponse(url="/admin/login", status_code=302)

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "admin_user": current_admin.get("username"),
            "bot_username": settings.TELEGRAM_BOT_USERNAME,
            "bot_token": settings.TELEGRAM_BOT_TOKEN
        }
    )

@router.get("/api/admin/stats")
async def get_admin_stats(current_admin: dict = Depends(get_current_admin)):
    total_students = db.students.count_documents({})
    active_students = db.students.count_documents({"is_active": {"$ne": False}})

    # Calculate average attendance
    students_with_att = list(db.students.find(
        {"last_overall_percentage": {"$ne": None}},
        {"last_overall_percentage": 1}
    ))

    avg_pct = 0.0
    valid_count = 0
    for s in students_with_att:
        pct_str = s.get("last_overall_percentage", "")
        if pct_str:
            clean = pct_str.replace("%", "").strip()
            try:
                avg_pct += float(clean)
                valid_count += 1
            except ValueError:
                pass

    calculated_avg = f"{(avg_pct / valid_count):.2f}%" if valid_count > 0 else "0.0%"

    # Recent log counts
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_success = db.logs.count_documents({"timestamp": {"$gte": today_start}, "status": "SUCCESS"})
    today_failed = db.logs.count_documents({"timestamp": {"$gte": today_start}, "status": "FAILED"})

    return {
        "total_students": total_students,
        "active_students": active_students,
        "average_attendance": calculated_avg,
        "today_success_scrapes": today_success,
        "today_failed_scrapes": today_failed,
        "morning_schedule": f"{settings.MORNING_CRON_HOUR:02d}:{settings.MORNING_CRON_MINUTE:02d} AM",
        "night_schedule": f"{settings.NIGHT_CRON_HOUR:02d}:{settings.NIGHT_CRON_MINUTE:02d} PM"
    }

@router.get("/api/admin/students")
async def get_all_students(
    search: str = "",
    status_filter: str = "all",
    current_admin: dict = Depends(get_current_admin)
):
    query = {}
    if search:
        query["$or"] = [
            {"roll_no": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"telegram_chat_id": {"$regex": search, "$options": "i"}}
        ]

    if status_filter == "active":
        query["is_active"] = {"$ne": False}
    elif status_filter == "inactive":
        query["is_active"] = False

    students_cursor = db.students.find(query).sort("created_at", -1)
    results = []
    for s in students_cursor:
        results.append({
            "id": str(s["_id"]),
            "roll_no": s.get("roll_no"),
            "name": s.get("name"),
            "email": s.get("email"),
            "telegram_chat_id": s.get("telegram_chat_id"),
            "is_active": s.get("is_active", True),
            "last_overall_percentage": s.get("last_overall_percentage", "N/A"),
            "last_scraped_at": s.get("last_scraped_at").strftime("%d/%m/%Y %I:%M %p") if s.get("last_scraped_at") else None,
            "last_error": s.get("last_error"),
            "last_absences": s.get("last_absences", []),
            "subjects_count": len(s.get("last_attendance_data", []))
        })
    return {"students": results}

@router.get("/api/admin/students/{roll_no}")
async def get_student_details(roll_no: str, current_admin: dict = Depends(get_current_admin)):
    roll = roll_no.strip().upper()
    student = db.students.find_one({"roll_no": roll})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    recent_logs = list(db.logs.find({"roll_no": roll}).sort("timestamp", -1).limit(10))
    formatted_logs = []
    for l in recent_logs:
        formatted_logs.append({
            "status": l.get("status"),
            "overall_percentage": l.get("overall_percentage"),
            "triggered_by": l.get("triggered_by"),
            "error_message": l.get("error_message"),
            "absences": l.get("absences", []),
            "timestamp": l.get("timestamp").strftime("%d/%m/%Y %I:%M %p") if l.get("timestamp") else ""
        })

    return {
        "student": {
            "roll_no": student.get("roll_no"),
            "name": student.get("name"),
            "email": student.get("email"),
            "telegram_chat_id": student.get("telegram_chat_id"),
            "is_active": student.get("is_active", True),
            "last_overall_percentage": student.get("last_overall_percentage"),
            "last_scraped_at": student.get("last_scraped_at").strftime("%d/%m/%Y %I:%M %p") if student.get("last_scraped_at") else None,
            "last_error": student.get("last_error"),
            "subjects": student.get("last_attendance_data", [])
        },
        "logs": formatted_logs
    }

@router.post("/api/admin/students")
async def admin_create_student(payload: StudentRegisterRequest, current_admin: dict = Depends(get_current_admin)):
    roll = payload.roll_no.strip().upper()
    existing = db.students.find_one({"roll_no": roll})
    if existing:
        raise HTTPException(status_code=400, detail="Student with this roll number already exists.")

    student_doc = {
        "name": payload.name.strip(),
        "roll_no": roll,
        "email": payload.email.strip().lower(),
        "telegram_chat_id": payload.telegram_chat_id.strip(),
        "erp_password": payload.erp_password.strip(),
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_scraped_at": None,
        "last_overall_percentage": None,
        "last_attendance_data": [],
        "last_error": None
    }
    db.students.insert_one(student_doc)
    return {"success": True, "message": f"Student {roll} created successfully"}

@router.put("/api/admin/students/{roll_no}")
async def admin_update_student(
    roll_no: str,
    payload: StudentUpdateRequest,
    current_admin: dict = Depends(get_current_admin)
):
    roll = roll_no.strip().upper()
    student = db.students.find_one({"roll_no": roll})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    update_fields = {"updated_at": datetime.utcnow()}
    if payload.name is not None:
        update_fields["name"] = payload.name.strip()
    if payload.email is not None:
        update_fields["email"] = payload.email.strip().lower()
    if payload.telegram_chat_id is not None:
        update_fields["telegram_chat_id"] = payload.telegram_chat_id.strip()
    if payload.erp_password is not None and payload.erp_password.strip():
        update_fields["erp_password"] = payload.erp_password.strip()
    if payload.is_active is not None:
        update_fields["is_active"] = payload.is_active

    db.students.update_one({"roll_no": roll}, {"$set": update_fields})
    return {"success": True, "message": f"Student {roll} updated successfully"}

@router.delete("/api/admin/students/{roll_no}")
async def admin_delete_student(roll_no: str, current_admin: dict = Depends(get_current_admin)):
    roll = roll_no.strip().upper()
    res = db.students.delete_one({"roll_no": roll})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"success": True, "message": f"Student {roll} deleted successfully"}

@router.post("/api/admin/students/{roll_no}/trigger")
async def admin_trigger_single_student(
    roll_no: str,
    background_tasks: BackgroundTasks,
    current_admin: dict = Depends(get_current_admin)
):
    roll = roll_no.strip().upper()
    student = db.students.find_one({"roll_no": roll})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    background_tasks.add_task(process_single_student, student, "MANUAL_ADMIN_SINGLE")
    return {"success": True, "message": f"Attendance scrape triggered in background for {roll}"}

@router.post("/api/admin/trigger-all")
async def admin_trigger_all_students(
    background_tasks: BackgroundTasks,
    current_admin: dict = Depends(get_current_admin)
):
    background_tasks.add_task(run_batch_attendance, "MANUAL_ADMIN_ALL")
    return {"success": True, "message": "Batch attendance scrape triggered for all active students."}

@router.get("/api/admin/logs")
async def get_admin_logs(limit: int = 50, current_admin: dict = Depends(get_current_admin)):
    logs_cursor = db.logs.find().sort("timestamp", -1).limit(limit)
    formatted = []
    for l in logs_cursor:
        formatted.append({
            "id": str(l["_id"]),
            "roll_no": l.get("roll_no"),
            "student_name": l.get("student_name"),
            "status": l.get("status"),
            "overall_percentage": l.get("overall_percentage"),
            "triggered_by": l.get("triggered_by"),
            "error_message": l.get("error_message"),
            "absences_count": len(l.get("absences", [])),
            "timestamp": l.get("timestamp").strftime("%d/%m/%Y %I:%M:%S %p") if l.get("timestamp") else ""
        })
    return {"logs": formatted}

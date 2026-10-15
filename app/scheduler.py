import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.config import settings
from app.database import db
from app.scraper import scrape_student_attendance
from app.telegram_bot import telegram_service

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def process_single_student(student: dict, trigger_name: str) -> dict:
    """
    Executes scrape, comparison, DB updates and Telegram alert for a single student.
    """
    roll_no = student.get("roll_no")
    name = student.get("name", "Student")
    chat_id = student.get("telegram_chat_id")
    erp_pass = student.get("erp_password")
    prev_data = student.get("last_attendance_data")

    logger.info(f"Processing attendance check for {roll_no} (Trigger: {trigger_name})")

    result = scrape_student_attendance(roll_no, erp_pass, prev_data)
    now_dt = datetime.utcnow()

    if result["success"]:
        # Update student record
        db.students.update_one(
            {"_id": student["_id"]},
            {
                "$set": {
                    "last_scraped_at": now_dt,
                    "last_overall_percentage": result["overall_percentage"],
                    "last_attendance_data": result["subjects"],
                    "last_absences": result["absences"],
                    "last_error": None
                }
            }
        )

        # Record in logs - rewrite existing record for this student to save database memory
        db.logs.update_one(
            {"roll_no": roll_no},
            {
                "$set": {
                    "roll_no": roll_no,
                    "student_name": name,
                    "status": "SUCCESS",
                    "overall_percentage": result["overall_percentage"],
                    "subjects_count": len(result["subjects"]),
                    "absences": result["absences"],
                    "triggered_by": trigger_name,
                    "error_message": None,
                    "timestamp": now_dt
                }
            },
            upsert=True
        )

        # Send Telegram notification
        if chat_id:
            msg = telegram_service.format_attendance_message(
                name=name,
                roll_no=roll_no,
                overall_percentage=result["overall_percentage"],
                subjects=result["subjects"],
                absences=result["absences"]
            )
            telegram_service.send_message(chat_id, msg)

        return {"roll_no": roll_no, "success": True, "overall": result["overall_percentage"]}
    else:
        err_msg = result.get("error", "Unknown error")
        db.students.update_one(
            {"_id": student["_id"]},
            {
                "$set": {
                    "last_scraped_at": now_dt,
                    "last_error": err_msg
                }
            }
        )

        # Record in logs - rewrite existing record for this student on failure
        db.logs.update_one(
            {"roll_no": roll_no},
            {
                "$set": {
                    "roll_no": roll_no,
                    "student_name": name,
                    "status": "FAILED",
                    "error_message": err_msg,
                    "triggered_by": trigger_name,
                    "timestamp": now_dt
                }
            },
            upsert=True
        )

        if chat_id:
            telegram_service.send_message(
                chat_id,
                f"⚠️ *Attendance Alert Notice*\n"
                f"We could not refresh your attendance from ERP: _{err_msg}_\n"
                f"Please verify your credentials or check if ERP is accessible."
            )

        return {"roll_no": roll_no, "success": False, "error": err_msg}

def scheduled_job_morning():
    logger.info("⏰ Morning 8:00 AM Attendance Job Started")
    run_batch_attendance("SCHEDULED_MORNING_8AM")

def scheduled_job_night():
    logger.info("⏰ Night 8:00 PM Attendance Job Started")
    run_batch_attendance("SCHEDULED_NIGHT_8PM")

def run_batch_attendance(trigger_name: str) -> dict:
    """
    Iterates through all active registered students and processes attendance.
    """
    students = list(db.students.find({"is_active": {"$ne": False}}))
    total = len(students)
    success_count = 0
    fail_count = 0

    logger.info(f"Starting batch attendance run '{trigger_name}' for {total} active student(s)")

    for s in students:
        try:
            res = process_single_student(s, trigger_name)
            if res.get("success"):
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"Error processing batch student {s.get('roll_no')}: {e}")
            fail_count += 1

    logger.info(f"Batch run '{trigger_name}' finished: Total={total}, Success={success_count}, Failed={fail_count}")
    return {"total": total, "success": success_count, "failed": fail_count}

def start_scheduler():
    if not scheduler.running:
        # Morning trigger: 8:00 AM
        scheduler.add_job(
            scheduled_job_morning,
            trigger=CronTrigger(hour=settings.MORNING_CRON_HOUR, minute=settings.MORNING_CRON_MINUTE),
            id="morning_attendance_job",
            replace_existing=True
        )

        # Night trigger: 8:00 PM (20:00)
        scheduler.add_job(
            scheduled_job_night,
            trigger=CronTrigger(hour=settings.NIGHT_CRON_HOUR, minute=settings.NIGHT_CRON_MINUTE),
            id="night_attendance_job",
            replace_existing=True
        )

        scheduler.start()
        logger.info(
            f"Scheduler started with triggers at 8:00 AM "
            f"and 8:00 PM (20:00) daily."
        )

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")

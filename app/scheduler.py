import os
import logging
import zoneinfo
import requests
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.config import settings
from app.database import db
from app.scraper import scrape_student_attendance
from app.telegram_bot import telegram_service

logger = logging.getLogger(__name__)

# Indian Standard Time (IST) Zone
IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")

scheduler = BackgroundScheduler(timezone=IST_TZ)

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
                    "last_absences": result.get("absences", []),
                    "last_presents": result.get("presents", []),
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
                    "absences": result.get("absences", []),
                    "presents": result.get("presents", []),
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
                absences=result.get("absences", []),
                presents=result.get("presents", [])
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

DEFAULT_SCHEDULES = [
    {"id": "morning", "name": "Morning Sync", "enabled": True, "time": "08:00"},
    {"id": "evening", "name": "Evening Sync", "enabled": True, "time": "20:00"}
]

def get_scheduler_config() -> dict:
    """
    Retrieves current schedule configuration from MongoDB settings collection.
    """
    try:
        if db.settings is not None:
            conf = db.settings.find_one({"key": "scheduler_config"})
            if conf:
                return {
                    "timezone": "Asia/Kolkata",
                    "schedules": conf.get("schedules", DEFAULT_SCHEDULES),
                    "keep_alive_enabled": conf.get("keep_alive_enabled", True)
                }
    except Exception as e:
        logger.warning(f"Could not load scheduler config from DB: {e}")

    return {
        "timezone": "Asia/Kolkata",
        "schedules": DEFAULT_SCHEDULES,
        "keep_alive_enabled": True
    }

def save_scheduler_config(schedules: list, keep_alive_enabled: bool = True) -> dict:
    """
    Saves new schedule configuration to MongoDB and immediately reloads active scheduler jobs.
    """
    now_dt = datetime.utcnow()
    config_doc = {
        "key": "scheduler_config",
        "timezone": "Asia/Kolkata",
        "schedules": schedules,
        "keep_alive_enabled": keep_alive_enabled,
        "updated_at": now_dt
    }

    if db.settings is not None:
        db.settings.update_one(
            {"key": "scheduler_config"},
            {"$set": config_doc},
            upsert=True
        )

    # Immediately reload jobs with new timings in memory
    reload_scheduler_jobs()
    return config_doc

def reload_scheduler_jobs():
    """
    Dynamically clears and registers cron jobs from MongoDB settings using Asia/Kolkata (IST).
    """
    conf = get_scheduler_config()
    schedules = conf.get("schedules", DEFAULT_SCHEDULES)
    keep_alive = conf.get("keep_alive_enabled", True)

    # Remove existing sync jobs
    for job in scheduler.get_jobs():
        if job.id.startswith("cron_sync_"):
            try:
                scheduler.remove_job(job.id)
            except Exception:
                pass

    registered = []
    for item in schedules:
        if not item.get("enabled", True):
            continue

        item_id = item.get("id", "custom")
        job_id = f"cron_sync_{item_id}"
        time_str = item.get("time", "08:00").strip()
        name = item.get("name", f"Attendance Sync ({time_str})")

        try:
            parts = time_str.split(":")
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
        except Exception:
            h, m = 8, 0

        # Closure generator for job action
        def create_job_action(trigger_label):
            def _action():
                logger.info(f"⏰ Triggering scheduled attendance sync: {trigger_label}")
                run_batch_attendance(trigger_label)
            return _action

        action_label = f"SCHEDULED_{name.upper().replace(' ', '_')}"
        trigger = CronTrigger(hour=h, minute=m, timezone=IST_TZ)

        scheduler.add_job(
            create_job_action(action_label),
            trigger=trigger,
            id=job_id,
            name=name,
            replace_existing=True
        )
        registered.append({"id": job_id, "name": name, "time": f"{h:02d}:{m:02d} IST"})

    # Setup or remove keep-alive self-ping (pings every 10 minutes to prevent Render free-tier sleep)
    if keep_alive:
        if not scheduler.get_job("keep_alive_ping_job"):
            scheduler.add_job(
                keep_alive_ping,
                trigger=IntervalTrigger(minutes=10),
                id="keep_alive_ping_job",
                name="Render Free Tier Keep-Alive",
                replace_existing=True
            )
            logger.info("Keep-alive 10-minute heartbeat enabled to prevent Render from sleeping.")
    else:
        if scheduler.get_job("keep_alive_ping_job"):
            scheduler.remove_job("keep_alive_ping_job")

    logger.info(f"Scheduler updated. Active IST Cron Jobs: {registered}")

def get_next_run_times() -> list:
    """
    Returns human-readable next fire times in IST for all active scheduled jobs.
    """
    now_ist = datetime.now(IST_TZ)
    jobs_info = []

    for job in scheduler.get_jobs():
        if job.id.startswith("cron_sync_"):
            next_fire = getattr(job, "next_run_time", None)
            if not next_fire and hasattr(job, "trigger"):
                try:
                    next_fire = job.trigger.get_next_fire_time(None, now_ist)
                except Exception:
                    next_fire = None

            if next_fire:
                # Convert next_fire to IST if not already
                if next_fire.tzinfo is None:
                    next_fire = next_fire.replace(tzinfo=IST_TZ)
                else:
                    next_fire = next_fire.astimezone(IST_TZ)

                diff = (next_fire - now_ist).total_seconds()
                hours = int(diff // 3600)
                mins = int((diff % 3600) // 60)
                time_left = f"in {hours}h {mins}m" if hours > 0 else f"in {mins}m"

                jobs_info.append({
                    "job_id": job.id,
                    "name": job.name,
                    "next_run_ist": next_fire.strftime("%d %b %Y, %I:%M %p IST"),
                    "time_until": time_left
                })

    return jobs_info

def keep_alive_ping():
    """
    Pings the application health endpoint every 10 minutes to prevent Render from going to sleep.
    """
    try:
        public_url = os.getenv("RENDER_EXTERNAL_URL") or "https://lbrcesmartnoteattendence-1.onrender.com"
        target = f"{public_url.rstrip('/')}/api/health"
        r = requests.get(target, timeout=10)
        logger.debug(f"Keep-alive self-ping response: {r.status_code}")
    except Exception as e:
        logger.debug(f"Keep-alive ping notice: {e}")

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
        scheduler.start()
        reload_scheduler_jobs()
        logger.info("BackgroundScheduler initialized and running in Asia/Kolkata (IST).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")

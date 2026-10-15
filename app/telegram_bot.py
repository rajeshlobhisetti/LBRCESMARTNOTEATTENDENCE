import logging
import threading
import time
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)

class TelegramBotService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.last_update_id = 0

    def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Sends a message to a specific Telegram chat_id.
        """
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": str(chat_id).strip(),
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                return True
            else:
                logger.error(f"Telegram sendMessage failed ({res.status_code}): {res.text}")
                # Fallback to plain text if Markdown parsing failed
                if "can't parse entities" in res.text:
                    payload.pop("parse_mode")
                    fallback_res = requests.post(url, json=payload, timeout=10)
                    return fallback_res.status_code == 200
                return False
        except Exception as e:
            logger.error(f"Telegram send_message error to {chat_id}: {e}")
            return False

    def format_attendance_message(
        self,
        name: str,
        roll_no: str,
        overall_percentage: str,
        subjects: List[Dict[str, Any]],
        absences: Optional[List[Dict[str, Any]]] = None,
        note: Optional[str] = None
    ) -> str:
        """
        Formats attendance data into a clean, readable Telegram message.
        Prominently highlights absentee warnings when missed classes are detected.
        """
        now = datetime.now().strftime("%d/%m/%Y %I:%M %p")

        if absences and len(absences) > 0:
            total_missed = sum(ab.get('classes_missed', 1) for ab in absences)
            msg = "🚨🚨 *ATTENDANCE WARNING: ABSENCE DETECTED!* 🚨🚨\n"
            msg += f"⚠️ *You were marked ABSENT in {total_missed} class(es)!*\n\n"
            msg += f"👤 Student: *{name}* (`{roll_no}`)\n"
            msg += f"🕐 Time: {now}\n"
            msg += f"📉 Overall Attendance: *{overall_percentage}*\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

            msg += "🔴 *MISSED CLASSES DETAILS:*\n\n"
            for ab in absences:
                sname = ab.get('subject', 'Subject')
                missed = ab.get('classes_missed', 1)
                before_att = f"{ab.get('before_present')}/{ab.get('before_held')}"
                now_att = f"{ab.get('now_present')}/{ab.get('now_held')}"
                msg += f"⚠️ *{sname}*\n"
                msg += f"   • Attendance: {before_att} ➔ *{now_att}*\n"
                msg += f"   • ❌ *Missed: {missed} class(es)*\n\n"

            msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
        else:
            msg = "📊 *LBRCE ATTENDANCE REPORT*\n"
            msg += "✅ *No New Absences Detected*\n\n"
            msg += f"👤 Student: *{name}* (`{roll_no}`)\n"
            msg += f"🕐 Time: {now}\n"
            msg += f"📈 Overall Attendance: *{overall_percentage}*\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

        if subjects:
            msg += "📋 *CURRENT SUBJECT-WISE BREAKDOWN:*\n\n"
            for subj in subjects:
                sname = subj.get("subject", "Subject")
                held = subj.get("held", 0)
                present = subj.get("present", 0)
                pct = subj.get("percentage", "0%")
                msg += f"• *{sname}*\n"
                msg += f"   Attended: {present}/{held} classes ({pct})\n\n"
        else:
            msg += "ℹ️ _No subject records found on portal._\n\n"

        msg += "━━━━━━━━━━━━━━━━━━━━━━\n"

        # Mandatory attendance compliance warning
        try:
            pct_val = float(overall_percentage.replace('%', '').strip())
            if pct_val < 75.0:
                msg += f"⚠️ *ATTENDANCE DEFICIT ALERT:*\nYour current attendance is *{pct_val}%*, which is below the mandatory 75% threshold. Please attend upcoming classes to avoid condonation/detention.\n\n"
        except Exception:
            pass

        if note:
            msg += f"{note}\n"

        msg += "🔔 _Automated updates sent daily at 8:00 AM & 8:00 PM._"
        return msg

    def handle_command(self, chat_id: str, username: str, text: str):
        """
        Handles incoming telegram messages and commands from users.
        """
        clean_text = text.strip()
        command = clean_text.split(" ")[0].lower()

        student = db.students.find_one({"telegram_chat_id": str(chat_id)})

        if command in ["/start", "start"]:
            if student:
                resp = (
                    f"👋 *Welcome back, {student.get('name')}!*\n\n"
                    f"🎓 *Roll Number:* `{student.get('roll_no')}`\n"
                    f"🆔 *Your Chat ID:* `{chat_id}`\n"
                    f"🔔 *Status:* {'✅ Active' if student.get('is_active', True) else '⏸️ Paused'}\n\n"
                    f"You will automatically receive your attendance alerts every day at *8:00 AM* and *8:00 PM*.\n\n"
                    f"Commands available:\n"
                    f"• `/attendance` - Check your live attendance now\n"
                    f"• `/status` - View your registration status\n"
                    f"• `/help` - View help"
                )
            else:
                resp = (
                    f"👋 *Welcome to LBRCE Attendance Bot!*\n\n"
                    f"Your Telegram Chat ID is:\n"
                    f"👉 `{chat_id}` 👈 _(tap to copy)_\n\n"
                    f"📝 *How to activate your alerts:*\n"
                    f"1. Copy your Chat ID above: `{chat_id}`\n"
                    f"2. Visit our student registration portal\n"
                    f"3. Enter your Name, Roll Number, ERP Password & this Chat ID\n\n"
                    f"Once registered, you will get instant alerts twice a day (8:00 AM & 8:00 PM) and can check live attendance anytime with `/attendance`."
                )
            self.send_message(chat_id, resp)

        elif command in ["/attendance", "/check", "attendance"]:
            if not student:
                self.send_message(
                    chat_id,
                    f"⚠️ *Not Registered Yet*\n\n"
                    f"Your Telegram Chat ID is `{chat_id}`.\n"
                    f"Please register first on our web portal to link your LBRCE ERP account."
                )
                return

            self.send_message(chat_id, "⏳ *Fetching your live attendance from LBRCE ERP...*\nPlease wait a few seconds.")

            from app.scraper import scrape_student_attendance
            result = scrape_student_attendance(
                student["roll_no"],
                student["erp_password"],
                student.get("last_attendance_data")
            )

            if result["success"]:
                # Update database
                now_dt = datetime.utcnow()
                db.students.update_one(
                    {"_id": student["_id"]},
                    {
                        "$set": {
                            "last_scraped_at": now_dt,
                            "last_overall_percentage": result["overall_percentage"],
                            "last_attendance_data": result["subjects"],
                            "last_error": None
                        }
                    }
                )

                # Log - rewrite existing record for this student to save database memory
                db.logs.update_one(
                    {"roll_no": student["roll_no"]},
                    {
                        "$set": {
                            "roll_no": student["roll_no"],
                            "student_name": student["name"],
                            "status": "SUCCESS",
                            "overall_percentage": result["overall_percentage"],
                            "subjects_count": len(result["subjects"]),
                            "absences": result["absences"],
                            "triggered_by": "TELEGRAM_USER",
                            "error_message": None,
                            "timestamp": now_dt
                        }
                    },
                    upsert=True
                )

                msg = self.format_attendance_message(
                    name=student["name"],
                    roll_no=student["roll_no"],
                    overall_percentage=result["overall_percentage"],
                    subjects=result["subjects"],
                    absences=result["absences"]
                )
                self.send_message(chat_id, msg)
            else:
                err_text = result.get("error", "Failed to retrieve attendance.")
                # Record failure in logs rewrites existing log
                db.logs.update_one(
                    {"roll_no": student["roll_no"]},
                    {
                        "$set": {
                            "roll_no": student["roll_no"],
                            "student_name": student["name"],
                            "status": "FAILED",
                            "error_message": err_text,
                            "triggered_by": "TELEGRAM_USER",
                            "timestamp": datetime.utcnow()
                        }
                    },
                    upsert=True
                )

                self.send_message(
                    chat_id,
                    f"❌ *Attendance Check Failed*\n\n"
                    f"Error: {err_text}\n"
                    f"Please ensure your ERP credentials are valid."
                )

        elif command in ["/status", "status"]:
            if student:
                last_time = student.get("last_scraped_at")
                last_str = last_time.strftime("%d/%m/%Y %I:%M %p") if last_time else "Not scraped yet"
                resp = (
                    f"📋 *YOUR REGISTRATION STATUS*\n\n"
                    f"👤 *Name:* {student.get('name')}\n"
                    f"🎓 *Roll No:* `{student.get('roll_no')}`\n"
                    f"✉️ *Email:* {student.get('email')}\n"
                    f"🆔 *Chat ID:* `{student.get('telegram_chat_id')}`\n"
                    f"📊 *Last Attendance:* {student.get('last_overall_percentage', 'N/A')}\n"
                    f"🕐 *Last Checked:* {last_str}\n"
                    f"🔔 *Alerts:* {'Active (8 AM & 8 PM)' if student.get('is_active', True) else 'Paused'}\n\n"
                    f"Send `/attendance` to refresh your attendance now."
                )
            else:
                resp = (
                    f"ℹ️ *Status: Unregistered*\n\n"
                    f"Your Chat ID: `{chat_id}`\n"
                    f"Register on the web portal to activate your account."
                )
            self.send_message(chat_id, resp)

        elif command in ["/help", "help"]:
            resp = (
                f"🤖 *LBRCE Attendance Bot Help*\n\n"
                f"• `/start` - Start bot and show your Chat ID\n"
                f"• `/attendance` - Fetch latest attendance from ERP\n"
                f"• `/status` - Check your registration details\n"
                f"• `/help` - View this help menu\n\n"
                f"Notifications arrive automatically at 8:00 AM & 8:00 PM."
            )
            self.send_message(chat_id, resp)

        else:
            # Friendly fallback
            self.send_message(
                chat_id,
                f"Hi! Send `/attendance` to check your current attendance or `/help` for commands."
            )

    def _polling_loop(self):
        """
        Background polling thread that listens to Telegram updates.
        """
        logger.info("Telegram Bot polling thread started.")
        while self.is_running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self.last_update_id + 1, "timeout": 20}
                res = requests.get(url, params=params, timeout=25)

                if res.status_code == 200:
                    data = res.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        message = update.get("message")
                        if message and "text" in message:
                            chat_id = str(message["chat"]["id"])
                            text = message.get("text", "")
                            username = message.get("from", {}).get("username", "")
                            try:
                                self.handle_command(chat_id, username, text)
                            except Exception as cmd_err:
                                logger.error(f"Error handling Telegram command '{text}': {cmd_err}")
                else:
                    time.sleep(2)
            except requests.exceptions.RequestException:
                time.sleep(5)
            except Exception as e:
                logger.error(f"Error in Telegram polling loop: {e}")
                time.sleep(5)

    def start_polling(self):
        """
        Starts the polling thread in the background.
        """
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._polling_loop, daemon=True)
            self.thread.start()
            logger.info("Telegram Bot service started successfully.")

    def stop_polling(self):
        """
        Stops the polling thread.
        """
        self.is_running = False
        logger.info("Telegram Bot service stopping.")

telegram_service = TelegramBotService()

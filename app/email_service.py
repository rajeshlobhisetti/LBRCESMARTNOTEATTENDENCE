import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.config import settings

logger = logging.getLogger(__name__)

def send_registration_success_email(name: str, roll_no: str, to_email: str, telegram_chat_id: str) -> bool:
    """
    Sends a registration confirmation email to the student.
    Returns True if sent successfully, False otherwise.
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(
            f"SMTP credentials not fully configured in settings. Email to {to_email} was skipped. "
            f"(Configure SMTP_USER and SMTP_PASSWORD in .env or Admin Settings to enable live email delivery)."
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🎉 Registration Successful - LBRCE Attendance Alerts"
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL or settings.SMTP_USER}>"
        msg["To"] = to_email

        plain_text = f"""
Hello {name},

Congratulations! You have successfully registered for the LBRCE Attendance Notification Service.

Registration Details:
- Student Name: {name}
- Roll Number: {roll_no}
- Registered Email: {to_email}
- Telegram Chat ID: {telegram_chat_id}

Attendance Notifications:
Your attendance will be automatically checked and sent directly to your Telegram twice every day:
- Morning: 8:00 AM
- Night: 8:00 PM

You can also send /attendance to our Telegram bot @{settings.TELEGRAM_BOT_USERNAME} anytime for an instant report.

Warm regards,
LBRCE Automated Attendance Team
        """

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #333; }}
    .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }}
    .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: #ffffff; padding: 30px 25px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; }}
    .header p {{ margin: 8px 0 0; opacity: 0.9; font-size: 14px; }}
    .content {{ padding: 30px 25px; }}
    .badge {{ display: inline-block; background-color: #ecfdf5; color: #065f46; padding: 6px 14px; border-radius: 9999px; font-size: 13px; font-weight: 600; margin-bottom: 20px; }}
    .info-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin: 20px 0; }}
    .info-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px dashed #e2e8f0; font-size: 14px; }}
    .info-row:last-child {{ border-bottom: none; }}
    .label {{ color: #64748b; font-weight: 500; }}
    .value {{ color: #0f172a; font-weight: 600; }}
    .schedule-card {{ background: #eff6ff; border-left: 4px solid #3b82f6; padding: 15px; border-radius: 4px; margin: 20px 0; font-size: 14px; }}
    .btn {{ display: inline-block; background-color: #2563eb; color: #ffffff !important; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 14px; text-align: center; margin-top: 15px; }}
    .footer {{ text-align: center; font-size: 12px; color: #94a3b8; padding: 20px; border-top: 1px solid #f1f5f9; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>Lakireddy Bali Reddy College of Engineering</h1>
      <p>Automated Attendance Notification Service</p>
    </div>
    <div class="content">
      <div class="badge">✅ Registration Completed</div>
      <h2 style="margin-top: 0; color: #1e293b; font-size: 20px;">Welcome, {name}!</h2>
      <p style="color: #475569; line-height: 1.6; font-size: 14px;">
        You have successfully registered for automated attendance tracking. Our intelligent agents will monitor your ERP attendance and send timely reports directly to your Telegram.
      </p>

      <div class="info-box">
        <div class="info-row"><span class="label">Roll Number:</span> <span class="value">{roll_no}</span></div>
        <div class="info-row"><span class="label">Telegram Chat ID:</span> <span class="value">{telegram_chat_id}</span></div>
        <div class="info-row"><span class="label">Registered Email:</span> <span class="value">{to_email}</span></div>
        <div class="info-row"><span class="label">Status:</span> <span class="value" style="color: #10b981;">Active</span></div>
      </div>

      <div class="schedule-card">
        <strong>⏰ Daily Schedule:</strong>
        <p style="margin: 5px 0 0; color: #1e40af;">
          • Morning Report: <strong>8:00 AM</strong><br>
          • Evening Report: <strong>8:00 PM</strong>
        </p>
      </div>

      <p style="font-size: 14px; color: #475569;">
        Need an update right now? You can message our Telegram bot with <code>/attendance</code> at any time.
      </p>

      <div style="text-align: center; margin-top: 25px;">
        <a href="https://t.me/{settings.TELEGRAM_BOT_USERNAME}" class="btn">Open Telegram Bot</a>
      </div>
    </div>
    <div class="footer">
      This is an automated notification from LBRCE Attendance Bot. Please do not reply directly to this email.
    </div>
  </div>
</body>
</html>
        """

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            server.starttls()

        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(msg["From"], [to_email], msg.as_string())
        server.quit()

        logger.info(f"Registration email sent successfully to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send registration email to {to_email}: {e}")
        return False

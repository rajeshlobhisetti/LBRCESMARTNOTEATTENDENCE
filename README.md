# 🎓 LBRCE Attendance Notification & Scraper Platform

An end-to-end automated platform for **Lakireddy Bali Reddy College of Engineering (LBRCE)** students.
It features a student registration portal, automated web scraping agents logging into LBRCE ERP, twice-daily Telegram notifications (8:00 AM & 8:00 PM), registration confirmation emails, and an Admin Platform with full database and scheduler controls.

---

## 🌟 Key Features

1. **Student Registration Portal (`/` & `/register`)**:
   - Students register with: **Full Name**, **Roll Number** (ERP username), **Email Address**, **Telegram Chat ID**, and **ERP Password**.
   - Built-in guide explaining how to retrieve their Telegram Chat ID from the bot in seconds.
   - Optional live **"Verify ERP Login"** button to confirm ERP credentials before submitting.
   - Upon successful registration, the student receives:
     - 📩 **HTML Email Confirmation** with registration details and schedule.
     - 📱 **Telegram Welcome Notification** confirming automated alert activation.

2. **Multi-User Telegram Bot (`@LBRCEattendancebot`)**:
   - Uses Bot Token: `8523038213:AAErnH_G_r4mnCH1wfgBe-JTTFNjDgdjwXs`
   - Single bot serving all registered students individually via their unique `chat_id`.
   - Commands:
     - `/start`: Welcomes student, displays their numeric Chat ID formatted for one-tap copy.
     - `/attendance` (or `/check`): On-demand live scrape from LBRCE ERP and formatted report delivery.
     - `/status`: Shows current registration details and last scraped attendance.
     - `/help`: Detailed command list.

3. **Intelligent Web Scraping Agent (`scraper.py`)**:
   - Automated headless Chromium session logging into `https://erp.lbrce.ac.in/Login/`.
   - Handles ASP.NET postbacks and navigates to `StudentHistory.aspx`.
   - Parses overall attendance percentage and subject-wise breakdown (Classes held, attended, percentage).
   - Compares current attendance against previously stored records in MongoDB to detect newly missed classes.

4. **Automated Twice-Daily Cron Schedule**:
   - Powered by `APScheduler`.
   - Automatically runs twice every day:
     - ☀️ **Morning Report:** 8:00 AM
     - 🌙 **Night Report:** 8:00 PM
   - Scrapes all active students in MongoDB, logs results, and dispatches detailed cards to Telegram.

5. **Admin Platform (`/admin` & `/admin/dashboard`)**:
   - Secure JWT cookie-based admin authentication.
   - Default login: `admin` / `admin@lbrce2025` (configurable via `.env`).
   - Features:
     - 📊 **Metrics Dashboard**: Total students, active alerts, average college attendance, today's scrape success vs failure.
     - 👥 **Student Management**: Search, filter, inspect full subject-wise attendance breakdown, edit details, toggle active/paused status, delete records.
     - ⚡ **Manual Scraper Triggers**:
       - "Trigger Scrape for All Now": Immediately executes morning/night batch run for all students.
       - "Scrape & Notify Now": Immediately runs scrape and sends notification for a single student.
     - 📜 **Live Scraping Logs**: View real-time logs, timestamps, trigger sources, and error messages.

---

## 🏗️ Architecture

```
d:\lbrce-attendance\
├── app\
│   ├── config.py              # Environment variables & application settings
│   ├── database.py            # MongoDB Atlas connection & indexing
│   ├── models.py              # Pydantic schemas for students & admin
│   ├── scraper.py             # Headless Selenium LBRCE ERP scraper & difference engine
│   ├── telegram_bot.py        # Background Telegram long-polling service & commands
│   ├── email_service.py       # SMTP email dispatcher for registration confirmations
│   ├── scheduler.py           # APScheduler for 8:00 AM & 8:00 PM daily execution
│   ├── auth.py                # JWT creation, decoding & password hashing
│   ├── routes\
│   │   ├── student.py         # Student registration & verify ERP endpoints
│   │   └── admin.py           # Admin login, CRUD, triggers & log endpoints
│   └── templates\
│       ├── base.html          # Responsive base template with Tailwind CSS
│       ├── register.html      # Student registration portal with Telegram helper
│       ├── register_success.html # Success confirmation screen
│       ├── admin_login.html   # Admin login screen
│       └── admin_dashboard.html # Full-featured admin control panel
├── main.py                    # FastAPI entrypoint & lifecycle management
├── Dockerfile                 # Production Docker image with Chrome & Python
├── docker-compose.yml         # Containerized single-command deployment
├── requirements.txt           # Python dependencies
├── run.bat                    # One-click Windows starter
├── .env.example               # Template environment configuration
└── .env                       # Active environment configuration
```

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites
- Python 3.10+
- Google Chrome installed (for Selenium headless scraping)
- MongoDB Database (already configured with provided connection URI)

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)
The `.env` file is already pre-configured with your credentials:
```env
MONGODB_URI=mongodb+srv://surya:surya@cluster0.vyreenm.mongodb.net/attendence?retryWrites=true&w=majority
DB_NAME=attendence

TELEGRAM_BOT_TOKEN=8523038213:AAErnH_G_r4mnCH1wfgBe-JTTFNjDgdjwXs
TELEGRAM_BOT_USERNAME=LBRCEattendancebot

ERP_BASE_URL=https://erp.lbrce.ac.in

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin@lbrce2025
ADMIN_EMAIL=admin@lbrce.ac.in
JWT_SECRET=lbrce-super-secret-jwt-attendance-key-2025-secure

MORNING_CRON_HOUR=8
MORNING_CRON_MINUTE=0
NIGHT_CRON_HOUR=20
NIGHT_CRON_MINUTE=0
```

*(Optional: Set `SMTP_USER` and `SMTP_PASSWORD` with a Gmail App Password to enable live outgoing emails).*

### 4. Run the Application
Double-click `run.bat` or run:
```powershell
python main.py
```
The server will start at:
- **Student Registration Portal**: [http://localhost:8000](http://localhost:8000)
- **Admin Control Panel**: [http://localhost:8000/admin](http://localhost:8000/admin) (Login: `admin` / `admin@lbrce2025`)
- **API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🐳 Docker Deployment

The project includes a production-ready `Dockerfile` that packages **Google Chrome Stable** and all required font and rendering libraries:

```bash
docker-compose up --build -d
```
To view logs:
```bash
docker-compose logs -f
```

---

## ☁️ Cloud Deployment (Render, Railway, VPS)

### Deploying on a Linux VPS (Ubuntu/Debian):
1. Clone the repository onto your server.
2. Ensure Docker and Docker Compose are installed:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose
   ```
3. Start the service:
   ```bash
   sudo docker-compose up -d --build
   ```
4. Point your domain (e.g., `attendance.yourdomain.com`) to port 8000 using Nginx or Caddy with SSL.

---

## 💬 Telegram Bot Usage Guide

1. Open Telegram and search for [@LBRCEattendancebot](https://t.me/LBRCEattendancebot).
2. Tap **Start** or send `/start`.
3. The bot will send:
   ```
   👋 Welcome to LBRCE Attendance Bot!
   Your Telegram Chat ID is:
   👉 7985297498 👈 (tap to copy)
   ```
4. Copy the ID and register on [http://localhost:8000](http://localhost:8000).
5. Send `/attendance` at any time to receive an instant live report!

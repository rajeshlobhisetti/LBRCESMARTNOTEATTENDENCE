@echo off
echo ============================================================
echo   LBRCE Attendance Notification Service - Launching
echo ============================================================
echo.
echo Starting FastAPI Web Server, Telegram Bot & Cron Scheduler...
echo Portal will be available at: http://localhost:8000
echo Admin portal: http://localhost:8000/admin
echo.
python main.py
pause

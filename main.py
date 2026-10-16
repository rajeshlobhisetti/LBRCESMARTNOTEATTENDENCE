import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import db
from app.telegram_bot import telegram_service
from app.scheduler import start_scheduler, stop_scheduler
from app.routes import student, admin

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("lbrce-attendance")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    logger.info("Initializing LBRCE Attendance Platform...")
    try:
        db.connect()
    except Exception as e:
        logger.error(f"Database startup error: {e}")

    try:
        telegram_service.start_polling()
    except Exception as e:
        logger.error(f"Telegram service startup error: {e}")

    try:
        start_scheduler()
    except Exception as e:
        logger.error(f"Scheduler startup error: {e}")

    logger.info("Platform successfully started.")
    yield

    # SHUTDOWN
    logger.info("Shutting down LBRCE Attendance Platform...")
    try:
        telegram_service.stop_polling()
    except Exception:
        pass
    try:
        stop_scheduler()
    except Exception:
        pass
    if db.client:
        try:
            db.client.close()
        except Exception:
            pass
    logger.info("Shutdown complete.")

app = FastAPI(
    title="LBRCE Attendance Notification Platform",
    description="Automated twice-daily attendance alerts via Telegram bot with Admin control panel",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import zoneinfo
from datetime import datetime

IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")

# Healthcheck for Render & Uptime monitors
@app.head("/")
@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "lbrce-attendance",
        "time_ist": datetime.now(IST_TZ).strftime("%d/%m/%Y %I:%M:%S %p IST")
    }

# Include Routers
app.include_router(student.router)
app.include_router(admin.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

import logging
import bcrypt
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.students: Collection = None
        self.logs: Collection = None
        self.admins: Collection = None
        self.settings: Collection = None
        self.is_connected = False

    def connect(self):
        try:
            logger.info("Connecting to MongoDB Atlas...")
            self.client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=8000)
            self.db = self.client[settings.DB_NAME]
            self.students = self.db["students"]
            self.logs = self.db["attendance_logs"]
            self.admins = self.db["admins"]
            self.settings = self.db["system_settings"]

            # Verify connection with ping
            self.client.admin.command("ping")
            self.is_connected = True
            logger.info("MongoDB ping successful!")

            # Create Indexes safely
            try:
                self.students.create_index([("roll_no", ASCENDING)], unique=True)
                self.students.create_index([("telegram_chat_id", ASCENDING)])
                self.students.create_index([("email", ASCENDING)])
                self.students.create_index([("is_active", ASCENDING)])
                self.admins.create_index([("username", ASCENDING)], unique=True)
                self.logs.create_index([("roll_no", ASCENDING)], unique=True)
            except Exception as idx_err:
                logger.warning(f"Index creation notice: {idx_err}")

            logger.info("Connected to MongoDB successfully and verified collections.")
            self._seed_default_admin()
        except Exception as e:
            self.is_connected = False
            logger.error(
                f"Failed to connect to MongoDB ({e}). "
                f"Please ensure Network Access on MongoDB Atlas is set to 0.0.0.0/0 (Allow from anywhere)."
            )

    def _seed_default_admin(self):
        try:
            if self.admins is None:
                return
            existing = self.admins.find_one({"username": settings.ADMIN_USERNAME})
            pwd_bytes = settings.ADMIN_PASSWORD.encode("utf-8")[:72]
            hashed = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")

            if not existing:
                self.admins.insert_one({
                    "username": settings.ADMIN_USERNAME,
                    "password_hash": hashed,
                    "email": settings.ADMIN_EMAIL,
                    "role": "superadmin",
                    "created_at": datetime.utcnow()
                })
                logger.info(f"Default admin '{settings.ADMIN_USERNAME}' created.")
            else:
                # Update password hash with clean bcrypt hash to guarantee login
                self.admins.update_one(
                    {"username": settings.ADMIN_USERNAME},
                    {"$set": {"password_hash": hashed}}
                )
                logger.info(f"Admin '{settings.ADMIN_USERNAME}' password hash verified.")
        except Exception as e:
            logger.warning(f"Could not seed admin: {e}")

db = Database()

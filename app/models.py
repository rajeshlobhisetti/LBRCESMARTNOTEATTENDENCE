from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class StudentRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full Name of the student")
    roll_no: str = Field(..., min_length=5, max_length=20, description="LBRCE Student Roll Number (ERP Username)")
    email: str = Field(..., min_length=5, max_length=150, description="Student Email address for confirmation")
    telegram_chat_id: str = Field(..., min_length=5, max_length=50, description="Telegram Chat ID")
    erp_password: str = Field(..., min_length=3, max_length=100, description="LBRCE ERP Login Password")

class StudentUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    erp_password: Optional[str] = None
    is_active: Optional[bool] = None

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class VerifyERPRequest(BaseModel):
    roll_no: str
    erp_password: str

class SubjectAttendance(BaseModel):
    sno: str
    subject: str
    held: int
    present: int
    percentage: str

class AttendanceReport(BaseModel):
    roll_no: str
    overall_percentage: str
    subjects: List[SubjectAttendance]
    timestamp: str
    absences: List[Dict[str, Any]] = []

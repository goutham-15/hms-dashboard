from sqlalchemy import Column, Integer, String, DateTime, Date, JSON, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum
from app.utils.logger import get_logger

logger = get_logger(name="db_models")
Base = declarative_base()


class RiskStatusEnum(str, enum.Enum):
    CRITICAL = "Critical"
    HIGH_RISK = "High Risk"
    MODERATE_RISK = "Moderate Risk"
    HEALTHY = "Healthy"


class FacultyHealthRecord(Base):
    """
    SQLAlchemy model for faculty health records, aligned with hms_health_records table.
    """
    __tablename__ = "hms_health_records"

    id = Column(String(50), primary_key=True)
    
    # 1. Staff Details
    employee_id = Column(String(50), nullable=False)
    year = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(10), nullable=False)
    department = Column(String(50), nullable=False, index=True)
    screening_date = Column(Date, nullable=False)
    
    # 2. Dashboard Analytics
    health_score = Column(Integer, default=0)
    status = Column(SQLEnum(RiskStatusEnum, name="risk_status_enum"), nullable=False, index=True)
    active_flags = Column(JSONB, default=list) # Array of strings
    
    # 3. Thyrocare Data
    thyrocare_results = Column(JSONB, default=dict)
    
    # 4. SecondMedic Data
    secondmedic_results = Column(JSONB, default=dict)
    
    # 5. Report Content
    inference = Column(Text, nullable=True)
    suggestion = Column(JSONB, default=list) # Array of strings
    
    # 6. System Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<FacultyHealthRecord(employee_id='{self.employee_id}', year={self.year}, status='{self.status}')>"

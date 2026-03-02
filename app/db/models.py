from sqlalchemy import Column, Integer, String, DateTime, Date, JSON, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum
from app.utils.logger import get_logger


logger = get_logger(name="db_models")
Base = declarative_base()


class GenderEnum(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class ReportStatusEnum(str, enum.Enum):
    PRELIMINARY = "PRELIMINARY"
    FINAL = "FINAL"
    CORRECTED = "CORRECTED"


class MedicalReport(Base):
    __tablename__ = "medical_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Staff Details
    staff_id = Column(String(100), default="")
    staff_name = Column(String(255), default="")
    staff_designation = Column(String(255), default="")
    staff_department = Column(String(255), default="")
    staff_contact = Column(String(50), default="")
    staff_email = Column(String(255), default="")
    
    # Thyrocare Report Info
    thyrocare_report_id = Column(String(255), default="")
    thyrocare_report_version = Column(String(50), default="")
    thyrocare_date = Column(Date, nullable=True)
    thyrocare_generated_at = Column(DateTime, nullable=True)
    thyrocare_lab_name = Column(String(255), default="")
    thyrocare_lab_code = Column(String(100), default="")
    thyrocare_status = Column(SQLEnum(ReportStatusEnum), nullable=True)
    thyrocare_source_system = Column(String(100), default="")
    
    # Thyrocare Patient Details
    thyrocare_patient_id = Column(String(255), default="")
    thyrocare_patient_name = Column(String(255), default="")
    thyrocare_patient_age = Column(Integer, nullable=True)
    thyrocare_patient_gender = Column(SQLEnum(GenderEnum), nullable=True)
    thyrocare_referred_by = Column(String(255), default="")
    
    # Thyrocare Test Results (array stored as JSON)
    thyrocare_test_results = Column(JSON, default=list)
    
    # Thyrocare Summary
    thyrocare_total_tests_ready = Column(Integer, default=0)
    thyrocare_out_of_range_count = Column(Integer, default=0)
    
    # Thyrocare Doctor Verification
    thyrocare_doctor_name = Column(String(255), default="")
    thyrocare_doctor_designation = Column(String(255), default="")
    thyrocare_doctor_license_number = Column(String(100), default="")
    thyrocare_doctor_signed_at = Column(DateTime, nullable=True)
    
    # SecondMedic Report Info
    secondmedic_date = Column(Date, nullable=True)
    secondmedic_institution = Column(String(255), default="")
    secondmedic_case_ids = Column(JSON, nullable=True)
    
    # SecondMedic Patient Details
    secondmedic_patient_name = Column(String(255), default="")
    secondmedic_patient_age = Column(Integer, nullable=True)
    secondmedic_patient_gender = Column(SQLEnum(GenderEnum), nullable=True)
    
    # SecondMedic Diagnostics (array stored as JSON)
    secondmedic_diagnostics = Column(JSON, default=list)
    
    # SecondMedic Summary Findings
    secondmedic_summary_findings = Column(JSON, nullable=True)
    
    # Overall inference
    inference = Column(Text, nullable=False, default="")
    
    # Year tracking
    report_year = Column(Integer, nullable=True, index=True)
    
    # Audit fields
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

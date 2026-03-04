import hashlib
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime
import json
import decimal

from app.db.models import Base, FacultyHealthRecord
from app.models.medical_report import FacultyHealthProfile
from app.utils.config import settings
from app.utils.logger import get_logger

logger = get_logger(name="database")

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal types."""
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

class DatabaseManager:
    def __init__(self):
        self.connection_url = settings.database.url
        # For SQL Server, some drivers/versions might need special handling
        self.engine = create_engine(
            self.connection_url, 
            pool_pre_ping=True
        )
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)

    def create_tables(self):
        """Initialize database tables."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables verified/created.")

    def _generate_hash_id(self, employee_id: str, year: int) -> str:
        """Generate a 16-character hex hash from staff ID and year."""
        seed = f"{employee_id}_{year}"
        return hashlib.md5(seed.encode()).hexdigest()[:16]

    def upsert_faculty_health_record(self, profile: FacultyHealthProfile):
        """
        Inserts a new health record or updates an existing one.
        SQL Server compatible upsert.
        """
        staff = profile.staff_details
        year = int(staff.screening_date[:4])
        record_id = self._generate_hash_id(staff.employee_id, year)
        
        # Prepare data - manually serialize JSON for SQL Server nvarchar(max) columns
        record_data = {
            "name": staff.name,
            "age": staff.age,
            "gender": staff.gender,
            "department": staff.department or "STAFF", # Using "STAFF" as a generic fallback if inference fails
            "screening_date": datetime.strptime(staff.screening_date, "%Y-%m-%d").date(),
            "health_score": staff.overall_health_score or 0,
            "status": profile.status,
            "active_flags": json.dumps(profile.active_flags, cls=DecimalEncoder),
            "thyrocare_results": json.dumps(profile.thyrocare.model_dump(), cls=DecimalEncoder),
            "secondmedic_results": json.dumps(profile.secondmedic.model_dump(), cls=DecimalEncoder),
            "inference": profile.inference,
            "suggestion": json.dumps(profile.suggestion, cls=DecimalEncoder),
            "cost": json.dumps(profile.cost.model_dump(), cls=DecimalEncoder) # Entire cost JSON
        }

        session = self.Session()
        try:
            # Check if record exists
            existing_record = session.query(FacultyHealthRecord).filter_by(
                employee_id=staff.employee_id, 
                year=year
            ).first()

            if existing_record:
                # Update
                logger.info(f"Updating existing record for {staff.name} ({staff.employee_id}, {year})")
                for key, value in record_data.items():
                    setattr(existing_record, key, value)
            else:
                # Insert
                logger.info(f"Inserting new record for {staff.name} ({staff.employee_id}, {year})")
                new_record = FacultyHealthRecord(
                    id=record_id,
                    employee_id=staff.employee_id,
                    year=year,
                    **record_data
                )
                session.add(new_record)
            
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to upsert health record: {e}")
            raise
        finally:
            self.Session.remove()

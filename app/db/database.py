import hashlib
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime
import json
import decimal
import re

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

    def _parse_date(self, date_str: str) -> tuple[datetime, int]:
        """
        Parse various date formats and return (datetime, year).
        Handles formats like:
        - YYYY-MM-DD (standard)
        - DD/MM/YYYY
        - DD/MM (assumes current year 2026)
        - DD-MM-YYYY
        - YYYY/MM/DD
        """
        if not date_str or not isinstance(date_str, str):
            logger.warning(f"Invalid date string: {date_str}, using default 2026-01-01")
            return datetime(2026, 1, 1), 2026
        
        date_str = date_str.strip()
        
        # Try standard format first: YYYY-MM-DD
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt, dt.year
        except ValueError:
            pass
        
        # Try DD/MM/YYYY
        try:
            dt = datetime.strptime(date_str, "%d/%m/%Y")
            return dt, dt.year
        except ValueError:
            pass
        
        # Try DD/MM (assume current year 2026)
        try:
            dt = datetime.strptime(date_str, "%d/%m")
            dt = dt.replace(year=2026)
            return dt, 2026
        except ValueError:
            pass
        
        # Try DD-MM-YYYY
        try:
            dt = datetime.strptime(date_str, "%d-%m-%Y")
            return dt, dt.year
        except ValueError:
            pass
        
        # Try YYYY/MM/DD
        try:
            dt = datetime.strptime(date_str, "%Y/%m/%d")
            return dt, dt.year
        except ValueError:
            pass
        
        # Try to extract year from string using regex
        year_match = re.search(r'(20\d{2})', date_str)
        if year_match:
            year = int(year_match.group(1))
            logger.warning(f"Could not parse date '{date_str}', extracted year {year}, using {year}-01-01")
            return datetime(year, 1, 1), year
        
        # Fallback to current year
        logger.warning(f"Could not parse date '{date_str}', using default 2026-01-01")
        return datetime(2026, 1, 1), 2026

    def upsert_faculty_health_record(self, profile: FacultyHealthProfile, source_id: str = None):
        """
        Inserts a new health record or updates an existing one.
        SQL Server compatible upsert.
        
        Args:
            profile: FacultyHealthProfile object with extracted data
            source_id: Optional source_id from document processing (used as fallback if employee_id is missing)
        """
        staff = profile.staff_details
        
        # Parse date with robust handling
        screening_datetime, year = self._parse_date(staff.screening_date)
        
        # Use source_id as employee_id if employee_id is empty/missing
        # This ensures each unique document gets its own record
        employee_id = staff.employee_id if staff.employee_id and staff.employee_id.strip() else (source_id or "UNKNOWN")
        
        record_id = self._generate_hash_id(employee_id, year)
        
        # Prepare data - manually serialize JSON for SQL Server nvarchar(max) columns
        record_data = {
            "name": staff.name,
            "age": staff.age,
            "gender": staff.gender,
            "department": staff.department or "STAFF", # Using "STAFF" as a generic fallback if inference fails
            "screening_date": screening_datetime.date(),
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
                employee_id=employee_id, 
                year=year
            ).first()

            if existing_record:
                # Update
                logger.info(f"Updating existing record for {staff.name or 'Unknown'} ({employee_id}, {year})")
                for key, value in record_data.items():
                    setattr(existing_record, key, value)
            else:
                # Insert
                logger.info(f"Inserting new record for {staff.name or 'Unknown'} ({employee_id}, {year})")
                new_record = FacultyHealthRecord(
                    id=record_id,
                    employee_id=employee_id,
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

    def get_all_records(self):
        """Fetch all health records from database."""
        session = self.Session()
        try:
            records = session.query(FacultyHealthRecord).all()
            result = []
            for r in records:
                result.append({
                    "employee_id": r.employee_id,
                    "name": r.name,
                    "age": r.age,
                    "gender": r.gender,
                    "department": r.department,
                    "screening_date": r.screening_date.isoformat() if r.screening_date else None,
                    "health_score": r.health_score,
                    "status": r.status,
                    "active_flags": json.loads(r.active_flags) if isinstance(r.active_flags, str) else r.active_flags,
                    "thyrocare_results": json.loads(r.thyrocare_results) if isinstance(r.thyrocare_results, str) else r.thyrocare_results,
                    "secondmedic_results": json.loads(r.secondmedic_results) if isinstance(r.secondmedic_results, str) else r.secondmedic_results,
                    "inference": r.inference,
                    "suggestion": json.loads(r.suggestion) if isinstance(r.suggestion, str) else r.suggestion,
                })
            return result
        except Exception as e:
            logger.error(f"Failed to fetch records: {e}")
            raise
        finally:
            self.Session.remove()
    
    def search_records(self, query: str):
        """Search records by name, employee_id, or department."""
        session = self.Session()
        try:
            query_lower = f"%{query.lower()}%"
            records = session.query(FacultyHealthRecord).filter(
                (FacultyHealthRecord.name.ilike(query_lower)) |
                (FacultyHealthRecord.employee_id.ilike(query_lower)) |
                (FacultyHealthRecord.department.ilike(query_lower))
            ).all()
            
            result = []
            for r in records:
                result.append({
                    "employee_id": r.employee_id,
                    "name": r.name,
                    "age": r.age,
                    "gender": r.gender,
                    "department": r.department,
                    "screening_date": r.screening_date.isoformat() if r.screening_date else None,
                    "health_score": r.health_score,
                    "status": r.status,
                    "active_flags": json.loads(r.active_flags) if isinstance(r.active_flags, str) else r.active_flags,
                    "thyrocare_results": json.loads(r.thyrocare_results) if isinstance(r.thyrocare_results, str) else r.thyrocare_results,
                    "secondmedic_results": json.loads(r.secondmedic_results) if isinstance(r.secondmedic_results, str) else r.secondmedic_results,
                    "inference": r.inference,
                    "suggestion": json.loads(r.suggestion) if isinstance(r.suggestion, str) else r.suggestion,
                })
            return result
        except Exception as e:
            logger.error(f"Failed to search records: {e}")
            raise
        finally:
            self.Session.remove()

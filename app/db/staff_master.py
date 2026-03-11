"""
Staff Master Database Connection
Connects to external staff master database to fetch employee details.
"""
import pyodbc
from typing import Optional, Dict, Any
from app.utils.logger import get_logger
from app.models.medical_report import StaffDetails

logger = get_logger(name="staff_master")


class StaffMasterDB:
    """
    Connection to Staff Master database for fetching employee details.
    """
    
    def __init__(self):
        self.host = "35.200.132.227"
        self.username = "SECEdumateSP38"
        self.password = "$a!ra#MsM38EdUmAt3sP"
        self.database = "SAIRAMEC_EDUMATE"
        self.driver = "{ODBC Driver 17 for SQL Server}"
        
    def _get_connection(self):
        """Create database connection."""
        try:
            conn_str = (
                f"DRIVER={self.driver};"
                f"SERVER={self.host};"
                f"DATABASE={self.database};"
                f"UID={self.username};"
                f"PWD={self.password};"
                f"TrustServerCertificate=yes;"
            )
            return pyodbc.connect(conn_str, timeout=10)
        except Exception as e:
            logger.error(f"Failed to connect to Staff Master DB: {e}")
            raise
    
    def get_staff_details(self, staff_id: str) -> Optional[StaffDetails]:
        """
        Part 2 & 3: Fetch from DB and populate Pydantic model.
        """
        if not staff_id:
            return None
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    s.Staff_Code,
                    s.Staff_Name,
                    s.Gender,
                    s.Date_Of_Birth,
                    DATEDIFF(YEAR, s.Date_Of_Birth, GETDATE()) as Age,
                    b.Branch_Name as Department
                FROM T_CFG_STAFF_MASTER s
                LEFT JOIN T_CFG_BRANCH b ON s.Branch_Id = b.Branch_Id
                WHERE s.Staff_Code = ? AND s.Status = 1 AND s.Delete_Flag = 0
            """
            
            cursor.execute(query, (staff_id,))
            row = cursor.fetchone()
            
            if row:
                columns = [column[0] for column in cursor.description]
                data = dict(zip(columns, row))
                
                details = StaffDetails()
                details.employee_id = str(data.get('Staff_Code', staff_id))
                details.name = str(data.get('Staff_Name', ""))
                details.department = str(data.get('Department', ""))
                
                # Map gender
                gender_raw = str(data.get('Gender', "")).upper()
                if gender_raw in ['M', 'MALE']:
                    details.gender = 'MALE'
                elif gender_raw in ['F', 'FEMALE']:
                    details.gender = 'FEMALE'
                else:
                    details.gender = gender_raw
                
                # Map age
                try:
                    details.age = int(data.get('Age')) if data.get('Age') is not None else None
                except:
                    details.age = None
                
                cursor.close()
                conn.close()
                return details
            
            cursor.close()
            conn.close()
            return None
                
        except Exception as e:
            logger.error(f"Error fetching staff details for {staff_id}: {e}")
            return None

    def enrich_staff_details(self, staff_details_obj, first_page_text: str) -> None:
        """
        Legacy method preserved for compatibility. 
        Note: Extraction is now handled by LLM in extraction.py.
        """
        pass

"""
Staff Master Database Connection
Connects to external staff master database to fetch employee details.
"""
import pyodbc
import re
from typing import Optional, Dict, Any
from app.utils.logger import get_logger

logger = get_logger(name="staff_master")


class StaffMasterDB:
    """
    Connection to Staff Master database for fetching employee details.
    """
    
    def __init__(self):
        self.host = "35.200.132.227"
        self.username = "SECEdumateSP38"
        self.password = "$a!ra#MsM38EdUmAt3sP"
        self.database = "SAIRAMEC_EDUMATE"  # Confirmed database name
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
            )
            return pyodbc.connect(conn_str, timeout=10)
        except Exception as e:
            logger.error(f"Failed to connect to Staff Master DB: {e}")
            raise
    
    def extract_staff_id_from_text(self, text: str) -> Optional[str]:
        """
        Extract staff ID from SecondMedic report text using regex patterns.
        Handles both traditional formats and Docling markdown table format.
        
        Common patterns:
        - Staff ID: XXXXX
        - Staff Code: XXXXX
        - Employee ID: XXXXX
        - Emp ID: XXXXX
        - ID: XXXXX
        - Docling markdown table: | Emp ID | XXXXX |
        """
        if not text:
            return None
        
        # Try multiple patterns
        patterns = [
            # Docling markdown table format: | Emp ID | XXXXX |
            r'\|\s*Emp\s*ID\s*\|\s*([A-Z0-9]+)\s*\|',
            # Traditional colon/dash format
            r'Emp\s*ID\s*[:\-]?\s*([A-Z0-9]+)',
            r'Employee\s*(?:ID|Code)\s*[:\-]?\s*([A-Z0-9]+)',
            r'Staff\s*(?:ID|Code)\s*[:\-]?\s*([A-Z0-9]+)',
            r'ID\s*[:\-]?\s*([A-Z0-9]{4,})',
            r'Staff\s*[:\-]?\s*([A-Z0-9]{4,})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                staff_id = match.group(1).strip()
                
                # Remove "SECT" prefix if present (e.g., "SECT22EE01" -> "ET22EE01")
                # Also handle "SECTO" which might be OCR error for "SECT0"
                if staff_id.startswith("SECT"):
                    staff_id = staff_id[4:]  # Remove first 4 chars "SECT"
                elif staff_id.startswith("SECTO"):
                    # Handle "SECTO0ME01" -> "0ME01" (but we want "ET00ME01")
                    # This is likely "SECT00ME01" with OCR error
                    staff_id = "ET" + staff_id[5:]  # Remove "SECTO" and add "ET"
                elif staff_id.startswith("SITT"):
                    # Handle "SITT" prefix (e.g., "SITT17ME01" -> "IT17ME01")
                    staff_id = staff_id[2:]  # Remove first 2 chars "SI"
                
                logger.info(f"Extracted staff ID: {staff_id}")
                return staff_id
        
        logger.warning("Could not extract staff ID from text")
        return None
    
    def get_staff_details(self, staff_code: str) -> Optional[Dict[str, Any]]:
        """
        Fetch staff details from T_CFG_STAFF_MASTER table with department/branch info.
        
        Args:
            staff_code: The staff code/ID to lookup
            
        Returns:
            Dictionary with staff details or None if not found
        """
        if not staff_code:
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
                    b.Branch_Name as Department,
                    b.Branch_Code as Department_Code,
                    d.Department_Name as Department_Full_Name,
                    s.Email_Official,
                    s.Present_Mobile_No,
                    s.Date_Of_Joining
                FROM T_CFG_STAFF_MASTER s
                LEFT JOIN T_CFG_BRANCH b ON s.Branch_Id = b.Branch_Id
                LEFT JOIN T_CFG_DEPARTMENT d ON b.Department_Id = d.Department_Id
                WHERE s.Staff_Code = ? AND s.Status = 1 AND s.Delete_Flag = 0
            """
            
            cursor.execute(query, (staff_code,))
            row = cursor.fetchone()
            
            if row:
                # Convert row to dictionary
                columns = [column[0] for column in cursor.description]
                staff_data = dict(zip(columns, row))
                
                logger.info(f"Found staff details for {staff_code}: {staff_data.get('Staff_Name')} - {staff_data.get('Department')}")
                
                cursor.close()
                conn.close()
                
                return staff_data
            else:
                logger.warning(f"No staff found with code: {staff_code}")
                cursor.close()
                conn.close()
                return None
                
        except Exception as e:
            logger.error(f"Error fetching staff details for {staff_code}: {e}")
            return None
    
    def enrich_staff_details(self, staff_details_obj, first_page_text: str) -> None:
        """
        Enrich staff details object with data from Staff Master DB.
        
        Args:
            staff_details_obj: StaffDetails pydantic object to enrich
            first_page_text: Text from first page to extract staff ID
        """
        # Extract staff ID from text
        staff_id = self.extract_staff_id_from_text(first_page_text)
        
        if not staff_id:
            logger.warning("Could not extract staff ID, skipping Staff Master lookup")
            return
        
        # Fetch from database
        staff_data = self.get_staff_details(staff_id)
        
        if not staff_data:
            logger.warning(f"No data found in Staff Master for {staff_id}")
            return
        
        # Enrich the staff details object
        if staff_data.get('Staff_Code'):
            staff_details_obj.employee_id = staff_data['Staff_Code']
        
        if staff_data.get('Staff_Name'):
            staff_details_obj.name = staff_data['Staff_Name']
        
        if staff_data.get('Gender'):
            # Normalize gender
            gender = staff_data['Gender'].upper()
            if gender in ['M', 'MALE']:
                staff_details_obj.gender = 'MALE'
            elif gender in ['F', 'FEMALE']:
                staff_details_obj.gender = 'FEMALE'
            else:
                staff_details_obj.gender = gender
        
        if staff_data.get('Age'):
            staff_details_obj.age = int(staff_data['Age'])
        
        if staff_data.get('Department'):
            staff_details_obj.department = staff_data['Department']
        
        if staff_data.get('Date_of_Birth'):
            # You can store DOB if needed
            pass
        
        logger.info(f"Successfully enriched staff details from Staff Master DB for {staff_id}")

"""
Regex-based extraction for staff details from medical reports.
This extracts basic identity information without using LLM.
"""
import re
from typing import Optional, Tuple
from app.models.medical_report import StaffDetails
from app.utils.logger import get_logger

logger = get_logger(name="regex_extraction")


def extract_staff_id(text: str) -> Optional[str]:
    """
    Extract staff ID using regex patterns.
    Extracts exactly as found in text - no validation, no preprocessing.
    """
    patterns = [
        r'Emp\s*ID[:\s|]+([A-Z0-9]+)',  # | Emp ID | SITT12IT01 | or Emp ID: SITT12IT01
        r'Employee\s*ID[:\s|]+([A-Z0-9]+)',  # Employee ID: SITT12IT01
        r'Staff\s*Code[:\s|]+([A-Z0-9]+)',  # Staff Code: SITT12IT01
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            staff_id = match.group(1).strip().upper()
            logger.info(f"Extracted Staff ID: {staff_id}")
            return staff_id
    
    logger.warning("No Staff ID found in text")
    return None


def extract_name(text: str, staff_id: Optional[str] = None) -> Optional[str]:
    """
    Extract staff name using regex patterns.
    Extracts exactly as found - no cleaning, no preprocessing.
    """
    patterns = [
        r'\|\s*Name\s*\|\s*([A-Z][A-Z\s]+?)\s*\|',  # | Name | JOHN DOE |
        r'Name[:\s]+([A-Z][A-Z\s]+?)(?:\s*\|)',  # Name: JOHN DOE |
        r'Patient\s*Name[:\s]+([A-Z][A-Z\s]+?)(?:\s*\|)',
        r'Staff\s*Name[:\s]+([A-Z][A-Z\s]+?)(?:\s*\|)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            name = match.group(1).strip().upper()
            logger.info(f"Extracted Name: {name}")
            return name
    
    logger.warning("No Name found in text")
    return None


def extract_age(text: str) -> Optional[int]:
    """
    Extract age using regex patterns.
    Extracts exactly as found - no validation.
    """
    patterns = [
        r'\|\s*Age\s*\|\s*(\d+)',  # | Age | 43 |
        r'Age[:\s]+(\d+)',  # Age: 43
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            age = int(match.group(1))
            logger.info(f"Extracted Age: {age}")
            return age
    
    logger.warning("No Age found in text")
    return None


def extract_gender(text: str) -> Optional[str]:
    """
    Extract gender using regex patterns.
    Extracts exactly as found - no normalization.
    """
    patterns = [
        r'\|\s*Gender\s*\|\s*(MALE|FEMALE|M|F)',  # | Gender | FEMALE |
        r'Gender[:\s]+(MALE|FEMALE|M|F)',  # Gender: Female
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            gender = match.group(1).strip().upper()
            logger.info(f"Extracted Gender: {gender}")
            return gender
    
    logger.warning("No Gender found in text")
    return None


def extract_screening_date(text: str) -> Optional[str]:
    """
    Extract screening date and convert to YYYY-MM-DD format.
    Only format conversion, no validation.
    """
    patterns = [
        r'Date[:\s]+(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',  # Date: 22/12/2025
        r'\|\s*Date\s*\|\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',  # | Date | 22/12/2025 |
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            
            # Handle 2-digit year
            if year < 100:
                year += 2000
            
            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            logger.info(f"Extracted Screening Date: {date_str}")
            return date_str
    
    logger.warning("No Screening Date found in text, using default")
    return "2026-01-01"


def extract_staff_details_from_text(text: str) -> StaffDetails:
    """
    Extract all staff details from text using regex.
    This is the main entry point for regex-based extraction.
    """
    logger.info("Starting regex-based staff details extraction...")
    
    # Extract fields
    staff_id = extract_staff_id(text)
    name = extract_name(text, staff_id)
    age = extract_age(text)
    gender = extract_gender(text)
    screening_date = extract_screening_date(text)
    
    # Create StaffDetails object
    staff_details = StaffDetails(
        employee_id=staff_id or "",
        name=name or "",
        age=age or 0,
        gender=gender or "",
        department="",  # Will be filled from Staff Master DB
        screening_date=screening_date or "2026-01-01",
        overall_health_score=None  # Will be filled by LLM inference
    )
    
    logger.info(f"Regex extraction complete: ID={staff_details.employee_id}, Name={staff_details.name}, Age={staff_details.age}, Gender={staff_details.gender}")
    
    return staff_details

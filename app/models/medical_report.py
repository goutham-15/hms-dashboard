from enum import Enum
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field
import datetime as dt


class GenderEnum(str, Enum):
    """Patient gender classification"""
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class ReportStatusEnum(str, Enum):
    """Medical report status"""
    PRELIMINARY = "PRELIMINARY"
    FINAL = "FINAL"
    CORRECTED = "CORRECTED"


class ResultFlagEnum(str, Enum):
    """Test result flag indicating if value is within normal range"""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReferenceRange(BaseModel):
    """Reference range for lab test results"""
    low: Optional[float] = Field(None, description="Extract the lower bound numeric value of the normal/reference range for this test. Look for patterns like '12.0 - 16.0' or 'Normal: 12-16' and extract the first number.")
    high: Optional[float] = Field(None, description="Extract the upper bound numeric value of the normal/reference range for this test. Look for patterns like '12.0 - 16.0' or 'Normal: 12-16' and extract the second number.")
    text: Optional[str] = Field("", description="Extract the complete reference range text as written in the report, including units. Example: '12.0 - 16.0 g/dL' or '< 200 mg/dL'")


class TestResult(BaseModel):
    """Individual lab test result from Thyrocare"""
    panel_name: Optional[str] = Field("", description="Extract the test panel or group name (e.g., 'Complete Blood Count', 'Lipid Profile', 'Thyroid Profile'). Look for section headers or panel names in the report.")
    category: Optional[str] = Field("", description="Extract the medical category or department (e.g., 'Hematology', 'Biochemistry', 'Endocrinology'). Often found near the panel name.")
    test_code: Optional[str] = Field("", description="Extract the laboratory test code or identifier if present (e.g., 'CBC001', 'LIP002'). Usually alphanumeric codes near test names.")
    test_name: str = Field(..., description="Extract the specific test name exactly as written (e.g., 'Hemoglobin', 'Total Cholesterol', 'TSH'). This is required.")
    value: float = Field(..., description="Extract the numeric test result value. Convert to float. Look for the measurement value in the results column. This is required.")
    units: str = Field(..., description="Extract the unit of measurement (e.g., 'g/dL', 'mg/dL', 'mIU/L', '%'). Usually appears right after the numeric value. This is required.")
    reference_range: Optional[ReferenceRange] = Field(None, description="Extract the reference/normal range information if provided in the report.")
    result_flag: Optional[ResultFlagEnum] = Field(None, description="Determine if the result is LOW, NORMAL, HIGH, or CRITICAL by comparing the value to the reference range. Look for flags, arrows, or indicators in the report.")
    interpretation: Optional[str] = Field("", description="Extract any additional notes, comments, or interpretation text associated with this specific test result.")


class DiagnosticMetric(BaseModel):
    """Quantitative measurement from diagnostic test"""
    parameter: Optional[str] = Field("", description="Extract the name of the measured parameter from diagnostic reports (e.g., 'Cardiothoracic Ratio', 'Liver Size', 'Ejection Fraction').")
    value: Optional[float] = Field(None, description="Extract the numeric measurement value for this parameter. Convert to float.")
    units: Optional[str] = Field("", description="Extract the unit of measurement for this parameter (e.g., 'cm', 'mm', 'ratio', '%', 'mL').")


class DiagnosticEntry(BaseModel):
    """Diagnostic test entry from SecondMedic"""
    test_category: str = Field(..., description="Extract the category or type of diagnostic test (e.g., 'Radiology', 'Ultrasound', 'ECG', 'CT Scan', 'MRI'). Look for section headers or test type labels. This is required.")
    test_name: str = Field(..., description="Extract the specific diagnostic procedure name (e.g., 'Chest X-Ray', 'Abdominal Ultrasound', '2D Echo'). This is required.")
    findings: Optional[Union[str, dict[str, Any]]] = Field(None, description="Extract the findings or observations from the diagnostic test. Can be plain text (e.g., 'Clear lung fields bilaterally') or structured by organ/system (e.g., {'liver': 'Normal', 'kidneys': 'Normal'}). Extract all descriptive text about what was observed.")
    metrics: Optional[List[DiagnosticMetric]] = Field(None, description="Extract any quantitative measurements mentioned in the diagnostic report (e.g., organ sizes, ratios, volumes). Create a list of DiagnosticMetric objects.")
    impression: Optional[str] = Field("", description="Extract the doctor's impression, conclusion, or diagnosis for this specific diagnostic test. Usually labeled as 'Impression:', 'Conclusion:', or 'Diagnosis:'.")


class ThyrocareReportInfo(BaseModel):
    """Thyrocare lab report information"""
    report_id: str = Field(..., description="Extract the unique report identifier or report number. Look for 'Report ID', 'Report No', 'Lab No', or similar labels. This is required.")
    report_version: Optional[str] = Field("", description="Extract the report version if mentioned (e.g., 'v1.0', 'Version 2'). May not always be present.")
    report_date: dt.date = Field(..., description="Extract the report date. Look for 'Report Date', 'Collection Date', 'Date', or timestamp. Convert to YYYY-MM-DD format. This is required.")
    generated_at: Optional[dt.datetime] = Field(None, description="Extract the timestamp when the report was generated if available. Look for 'Generated at', 'Printed on', or similar. Convert to ISO datetime format.")
    lab_name: str = Field(..., description="Extract the laboratory name (e.g., 'Thyrocare Technologies Ltd', 'Thyrocare Labs'). Usually at the top of the report. This is required.")
    lab_code: Optional[str] = Field("", description="Extract the laboratory code or branch code if present (e.g., 'THY001', 'MUM-001').")
    status: Optional[ReportStatusEnum] = Field(None, description="Extract the report status. Look for 'Status:', 'Report Status:', or similar. Should be PRELIMINARY, FINAL, or CORRECTED.")
    source_system: Optional[str] = Field("", description="Extract the source system name if mentioned (e.g., 'LIMS', 'Laboratory Information System').")


class ThyrocarePatientDetails(BaseModel):
    """Patient details for Thyrocare report"""
    patient_id: Optional[str] = Field("", description="Extract the patient ID, patient number, or registration number. Look for 'Patient ID', 'Reg No', 'UHID', or similar labels.")
    name: str = Field(..., description="Extract the patient's full name. Look for 'Patient Name', 'Name', or similar labels. This is required.")
    age: int = Field(..., ge=0, le=130, description="Extract the patient's age in years. Look for 'Age', 'Age/Sex', or similar. Convert to integer. Must be between 0-130. This is required.")
    gender: GenderEnum = Field(..., description="Extract the patient's gender. Look for 'Gender', 'Sex', 'M/F', or similar. Convert to MALE, FEMALE, or OTHER. This is required.")
    referred_by: Optional[str] = Field("", description="Extract the referring doctor's name. Look for 'Referred By', 'Ref. By Dr.', 'Referring Physician', or similar labels.")


class ThyrocareSummary(BaseModel):
    """Summary statistics for Thyrocare lab tests"""
    total_tests_ready: Optional[int] = Field(default=0, ge=0, description="Count the total number of test results in the report. Sum all individual tests across all panels.")
    out_of_range_count: Optional[int] = Field(default=0, ge=0, description="Count how many test results are flagged as LOW, HIGH, or CRITICAL (not NORMAL). Look for abnormal flags or values outside reference ranges.")


class DoctorVerification(BaseModel):
    """Doctor verification details"""
    doctor_name: Optional[str] = Field("", description="Extract the verifying/signing doctor's name. Look for 'Verified by', 'Signed by', 'Pathologist', or signature sections at the bottom of the report.")
    designation: Optional[str] = Field("", description="Extract the doctor's designation or title (e.g., 'Pathologist', 'Senior Consultant', 'MD Pathology'). Usually near the doctor's name.")
    license_number: Optional[str] = Field("", description="Extract the doctor's medical license or registration number. Look for 'License No', 'Reg No', 'MCI No', or similar.")
    signed_at: Optional[dt.datetime] = Field(None, description="Extract the date and time when the report was signed or verified. Look for timestamps near the signature section. Convert to ISO datetime format.")


class ThyrocareReport(BaseModel):
    """Complete Thyrocare lab report"""
    report_info: ThyrocareReportInfo = Field(..., description="Extract all report metadata including report ID, date, lab name, and status from the header section of the Thyrocare report.")
    patient_details: ThyrocarePatientDetails = Field(..., description="Extract all patient demographic information including name, age, gender, patient ID, and referring doctor from the patient information section.")
    test_results: List[TestResult] = Field(..., description="Extract all individual test results from the report. Each test should include test name, value, units, reference range, and any flags. Create one TestResult object for each test in the report.")
    summary: Optional[ThyrocareSummary] = Field(None, description="Calculate summary statistics: count total tests and count how many are out of normal range.")
    doctor_verification: Optional[DoctorVerification] = Field(None, description="Extract doctor verification details from the signature section at the bottom of the report if present.")


class SecondMedicReportInfo(BaseModel):
    """SecondMedic comprehensive report information"""
    report_date: Optional[dt.date] = Field(None, description="Extract the report date from SecondMedic diagnostic reports. Look for 'Date', 'Report Date', or timestamps. Convert to YYYY-MM-DD format.")
    institution: Optional[str] = Field("", description="Extract the medical institution or hospital name (e.g., 'City Medical Center', 'Apollo Hospital'). Usually at the top of the report.")
    case_ids: Optional[dict[str, Any]] = Field(None, description="Extract any case IDs, accession numbers, or reference numbers. Create a dictionary with descriptive keys (e.g., {'radiology_id': 'RAD2024001', 'ultrasound_id': 'US2024045'}).")


class SecondMedicPatientDetails(BaseModel):
    """Patient details for SecondMedic report"""
    name: Optional[str] = Field("", description="Extract the patient's name from SecondMedic reports. Look for 'Patient Name', 'Name', or similar labels.")
    age: Optional[int] = Field(None, ge=0, le=130, description="Extract the patient's age in years. Look for 'Age' field. Convert to integer between 0-130.")
    gender: Optional[GenderEnum] = Field(None, description="Extract the patient's gender. Look for 'Gender', 'Sex' fields. Convert to MALE, FEMALE, or OTHER.")


class SecondMedicReport(BaseModel):
    """Complete SecondMedic comprehensive diagnostic report"""
    report_info: SecondMedicReportInfo = Field(..., description="Extract report metadata including date, institution name, and any case/accession numbers from the header section.")
    patient_details: SecondMedicPatientDetails = Field(..., description="Extract patient information including name, age, and gender from the patient details section.")
    diagnostics: List[DiagnosticEntry] = Field(..., description="Extract all diagnostic test entries. For each diagnostic procedure (X-Ray, Ultrasound, CT, etc.), create a DiagnosticEntry with test category, test name, findings, measurements, and impression. Extract all diagnostic sections from the report.")
    summary_findings: Optional[List[str]] = Field(None, description="Extract overall summary statements, conclusions, or recommendations that apply to the entire report. Look for 'Summary', 'Overall Impression', 'Recommendations' sections. Create an array of individual findings.")


class StaffDetails(BaseModel):
    """Medical staff member details"""
    staff_id: Optional[str] = Field("", description="Extract the staff member's unique identifier or employee ID if present in the document.")
    name: Optional[str] = Field("", description="Extract the name of the medical staff member who handled, reviewed, or processed this report. Look for 'Reviewed by', 'Processed by', or staff signatures.")
    designation: Optional[str] = Field("", description="Extract the staff member's job title or role (e.g., 'Senior Consultant', 'Medical Officer', 'Lab Technician').")
    department: Optional[str] = Field("", description="Extract the department name where the staff member works (e.g., 'Pathology', 'Radiology', 'Laboratory').")
    contact: Optional[str] = Field("", description="Extract the staff member's contact phone number if present in the document.")
    email: Optional[str] = Field("", description="Extract the staff member's email address if present in the document.")


class MedicalReportData(BaseModel):
    """
    Unified medical report data structure combining staff details, 
    Thyrocare lab reports, SecondMedic diagnostic reports, and inference.
    
    This is the top-level structure for extracting and storing medical report data.
    """
    staff_details: Union[StaffDetails, dict[str, Any]] = Field(
        default_factory=dict,
        description="Extract information about the medical staff member who handled this report. Look for staff names, designations, departments in headers, footers, or signature sections. If no staff information is found, use empty dict {}."
    )
    thyrocare: Union[ThyrocareReport, dict[str, Any]] = Field(
        default_factory=dict,
        description="Extract Thyrocare lab report data if this is a Thyrocare report. Thyrocare reports contain lab test results with numeric values, units, and reference ranges. Look for 'Thyrocare' branding, test panels, and tabular test results. If this is not a Thyrocare report, use empty dict {}."
    )
    second_medic: Union[SecondMedicReport, dict[str, Any]] = Field(
        default_factory=dict,
        description="Extract SecondMedic comprehensive diagnostic report data if this is a SecondMedic report. SecondMedic reports contain diagnostic imaging results (X-Ray, Ultrasound, CT, MRI) with findings and impressions. Look for 'SecondMedic' branding or diagnostic imaging reports. If this is not a SecondMedic report, use empty dict {}."
    )
    inference: str = Field(
        "",
        description="Generate an overall medical inference, summary, or conclusion based on all the extracted data. Synthesize key findings from lab tests and diagnostics. Highlight any abnormal results, critical findings, or important observations. Provide recommendations if mentioned in the report. This should be a comprehensive summary in 2-5 sentences."
    )

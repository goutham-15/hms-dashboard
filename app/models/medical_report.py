from typing import Dict, Union, List, Literal, Optional
from pydantic import BaseModel, Field, RootModel, field_validator


# ---------- Shared Definitions ----------

class TestResult(BaseModel):
    name: str = Field(
        "",
        description="Name of the lab test (e.g., FBS, HbA1c, Cholesterol)."
    )
    value: Union[float, int, str] = Field(
        "",
        description="Measured value of the lab test as reported (numeric or text exactly as in report)."
    )
    unit: str = Field(
        "",
        description="Unit of measurement for the lab test (e.g., mg/dL, mmol/L, IU/L)."
    )
    ref_range: str = Field(
        "",
        description="Reference or normal range mentioned in the report (keep original formatting)."
    )
    status: Literal[
        "Normal",
        "High",
        "Low",
        "Abnormal",
        "Deficient",
        "Insufficient",
    ] | str = Field(
        "",
        description="Clinical status of the test compared to reference range."
    )


class TestGroup(RootModel[List[TestResult]]):
    root: List[TestResult] = Field(default_factory=list)


class ImagingResult(BaseModel):
    findings: str = Field(
        "",
        description="Objective findings described in the imaging report."
    )
    impression: str = Field(
        "",
        description="Doctor's final impression or conclusion from the imaging report."
    )


# ---------- Core Models ----------

class StaffDetails(BaseModel):
    employee_id: str = Field(
        "",
        description="Unique alphanumeric identifier for the staff member. Extract ONLY the ID part."
    )
    name: str = Field(
        "",
        description="Full name of the faculty or staff member. Extract ONLY the name part, excluding any concatenated ID."
    )
    age: int = Field(
        18,
        ge=18,
        description="Age of the faculty member in completed years."
    )
    gender: Literal["Male", "Female", "Other"] | str = Field(
        "",
        description="Gender of the faculty member as stated in the report."
    )
    department: str = Field(
        "",
        description="Academic or administrative department the faculty belongs to."
    )
    screening_date: str = Field(
        "",
        description="Date of health screening in YYYY-MM-DD format."
    )
    overall_health_score: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Overall computed health score if provided in the report or dashboard."
    )

    @field_validator("employee_id", "name", "gender", "department", mode="after")
    @classmethod
    def uppercase_strings(cls, v: str) -> str:
        if isinstance(v, str):
            return v.upper()
        return v


class Thyrocare(BaseModel):
    diabetes_panel: TestGroup = Field(
        default_factory=TestGroup,
        description="Diabetes-related lab tests such as FBS, PPBS, HbA1c."
    )
    lipid_profile: TestGroup = Field(
        default_factory=TestGroup,
        description="Lipid profile tests such as Total Cholesterol, LDL, HDL, Triglycerides."
    )
    renal_kidney: TestGroup = Field(
        default_factory=TestGroup,
        description="Kidney function tests such as Urea, Creatinine, Uric Acid."
    )
    vitamins_hormones: TestGroup = Field(
        default_factory=TestGroup,
        description="Vitamin and hormone tests such as Vitamin D, Vitamin B12, TSH."
    )
    liver_function: TestGroup = Field(
        default_factory=TestGroup,
        description="Liver function tests such as SGOT, SGPT, Bilirubin."
    )


class SecondMedic(BaseModel):
    usg_abdomen: ImagingResult = Field(
        default_factory=ImagingResult,
        description="Ultrasound abdomen report findings and impression."
    )
    echocardiogram: ImagingResult = Field(
        default_factory=ImagingResult,
        description="Echocardiogram findings and cardiologist impression."
    )
    chest_xray: ImagingResult = Field(
        default_factory=ImagingResult,
        description="Chest X-ray findings and radiologist impression."
    )
    ecg: ImagingResult = Field(
        default_factory=ImagingResult,
        description="Electrocardiogram (ECG) findings and interpretation."
    )


class CostDetails(BaseModel):
    input_tokens: int = Field(0, description="Number of input tokens used.")
    output_tokens: int = Field(0, description="Number of output tokens generated.")
    cost: float = Field(0.0, description="Total estimated cost in USD.")


class FacultyHealthProfile(BaseModel):
    staff_details: StaffDetails = Field(
        default_factory=StaffDetails,
        description="Personal and employment details of the faculty member."
    )

    thyrocare: Thyrocare = Field(
        default_factory=Thyrocare,
        description="Biochemical lab test data extracted from Thyrocare reports."
    )

    secondmedic: SecondMedic = Field(
        default_factory=SecondMedic,
        description="Imaging and diagnostic impressions from SecondMedic reports."
    )

    inference: str = Field(
        "",
        description=(
            "Consolidated medical summary combining lab results and imaging findings. "
            "Write in clear clinical language."
        )
    )

    active_flags: List[str] = Field(
        default_factory=list,
        description=(
            "List of key flagged conditions inferred from reports "
            "(e.g., 'Diabetes Risk', 'Vitamin D Deficiency')."
        )
    )

    status: Literal[
        "Critical",
        "High Risk",
        "Moderate Risk",
        "Healthy",
    ] | str = Field(
        "",
        description="Overall health risk category derived from all available data."
    )

    suggestion: List[str] = Field(
        default_factory=list,
        description="Actionable medical or lifestyle recommendations for the faculty member."
    )

    cost: CostDetails = Field(
        default_factory=CostDetails,
        description="Detailed token usage and cost information for the extraction."
    )

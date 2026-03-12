"""
Pydantic schemas for the Faculty Health Monitoring Dashboard API.
Matches the JSON contract in BACKEND_API_TASKS.md.
"""
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# --- Reusable nested types ---

class LabTest(BaseModel):
    name: Optional[str] = None
    value: Optional[float | str] = None
    unit: Optional[str] = None
    ref_range: Optional[str] = None
    status: Optional[str] = None


class FindingsImpression(BaseModel):
    findings: Optional[str] = None
    impression: Optional[str] = None


class ThyrocareResults(BaseModel):
    diabetes_panel: list[LabTest] = Field(default_factory=list, alias="diabetes_panel")
    lipid_profile: list[LabTest] = Field(default_factory=list, alias="lipid_profile")
    renal_kidney: list[LabTest] = Field(default_factory=list, alias="renal_kidney")
    vitamins_hormones: list[LabTest] = Field(default_factory=list, alias="vitamins_hormones")
    liver_function: list[LabTest] = Field(default_factory=list, alias="liver_function")

    class Config:
        populate_by_name = True


class SecondmedicResults(BaseModel):
    usg_abdomen: Optional[FindingsImpression] = None
    echocardiogram: Optional[FindingsImpression] = None
    chest_xray: Optional[FindingsImpression] = None
    ecg: Optional[FindingsImpression] = None


# --- StaffRecord (single faculty) ---

class StaffRecord(BaseModel):
    id: str
    employee_id: str
    name: str
    age: int
    gender: Literal["MALE", "FEMALE"]
    department: str
    screening_date: str
    health_score: float
    status: Literal["Critical", "High Risk", "Moderate Risk", "Healthy"]
    active_flags: list[str] = Field(default_factory=list)
    thyrocare_results: dict[str, Any] = Field(default_factory=dict)
    secondmedic_results: dict[str, Any] = Field(default_factory=dict)
    inference: str = ""
    suggestion: list[str] = Field(default_factory=list)

    class Config:
        extra = "allow"  # allow thyrocare/secondmedic as raw dicts from DB


# --- StaffListResponse (paginated list) ---

class StaffListResponse(BaseModel):
    items: list[StaffRecord]
    total: int
    page: int
    limit: int


# --- DashboardData (summary + stats) ---

class DashboardSummary(BaseModel):
    total_faculty: int = 0
    critical: int = 0
    high_risk: int = 0
    moderate: int = 0
    healthy: int = 0
    avg_health_score: float = 0.0


class DashboardStats(BaseModel):
    status_distribution: dict[str, int] = Field(default_factory=dict)
    age_risk: dict[str, dict[str, int]] = Field(default_factory=dict)
    top_conditions: list[dict[str, Any]] = Field(default_factory=list)  # [{"name": str, "count": int}]
    department_distribution: dict[str, dict[str, int]] = Field(default_factory=dict)
    gender_comparison: dict[str, dict[str, Any]] = Field(default_factory=dict)


class DashboardData(BaseModel):
    summary: DashboardSummary
    stats: DashboardStats

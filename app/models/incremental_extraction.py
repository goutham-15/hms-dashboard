from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    THYROCARE = "THYROCARE"
    SECONDMEDIC = "SECONDMEDIC"
    UNKNOWN = "UNKNOWN"


class EvidenceItem(BaseModel):
    field_path: str = Field(
        ...,
        description="Dotted path to the field you updated (e.g., 'thyrocare.report_info.report_id', 'staff_details.name').",
    )
    page: int = Field(..., ge=1, description="1-based page number where this evidence comes from.")
    quote: str = Field(
        ...,
        description="A short verbatim snippet from page_text (<= 25 words) that supports the extracted value.",
    )
    value: Any = Field(..., description="The value you set for field_path.")


class ConflictItem(BaseModel):
    field_path: str = Field(..., description="Dotted path to the conflicting field.")
    page: int = Field(..., ge=1, description="1-based page number where the conflicting value appears.")
    existing_value: Any = Field(..., description="The value currently in state before this page.")
    new_value: Any = Field(..., description="The conflicting value found on this page.")
    quote: str = Field(..., description="A short verbatim snippet that shows the conflict.")
    note: Optional[str] = Field(
        "",
        description="Short note about why this is a conflict and what you recommend (do not overwrite automatically).",
    )


class IncrementalPageUpdate(BaseModel):
    doc_type: DocumentType = Field(
        default=DocumentType.UNKNOWN,
        description="Best guess of document type based only on page_text and current_state.",
    )
    updates: dict[str, Any] = Field(
        default_factory=dict,
        description="Partial structured updates inferred from this page only. Omit fields not supported by page_text.",
    )
    new_test_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Lab test results found on this page only (append-only; do not repeat previous pages).",
    )
    new_diagnostics: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Diagnostic entries found on this page only (append-only; do not repeat previous pages).",
    )
    running_summary: str = Field(
        default="",
        description="Short running summary so far (max ~8 lines). Must not include any hallucinated info.",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence items for every non-empty update you made in 'updates', 'new_test_results', or 'new_diagnostics'.",
    )
    conflicts: list[ConflictItem] = Field(
        default_factory=list,
        description="Any conflicts with current_state. Do not overwrite automatically; report them here.",
    )


class InferenceOnly(BaseModel):
    inference: str = Field(
        ...,
        description="2-5 sentence overall medical inference/summary based only on the provided structured state and running summary.",
    )


class IncrementalExtractionResult(BaseModel):
    doc_type: DocumentType = Field(default=DocumentType.UNKNOWN)
    data: "MedicalReportData" = Field(..., description="Final extracted medical report data.")
    running_summary: str = Field(default="", description="Final running summary.")
    evidence: list[EvidenceItem] = Field(default_factory=list)
    conflicts: list[ConflictItem] = Field(default_factory=list)


from app.models.medical_report import MedicalReportData  # noqa: E402

IncrementalExtractionResult.model_rebuild()

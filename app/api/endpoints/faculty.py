"""
GET /api/faculty, /api/faculty/flagged, /api/faculty/export, /api/faculty/:id
"""
import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Query, Path, HTTPException
from fastapi.responses import Response

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.api.services.faculty_data import (
    get_all_records,
    normalize_record,
)
from app.api.services.faculty_filter import filter_faculty, sort_faculty, paginate
from app.utils.api_cache import get_cached, set_cached
from app.schema.api_schemas import StaffRecord, StaffListResponse

router = APIRouter()

# Defaults per spec
DEFAULT_PAGE = 1
DEFAULT_LIMIT = 10

_API_PATH_FACULTY = "faculty"
_API_PATH_FACULTY_FLAGGED = "faculty/flagged"
_API_PATH_FACULTY_ID = "faculty/id"


def _list_response(
    search: Optional[str] = None,
    department: Optional[List[str]] = None,
    age_range: Optional[str] = None,
    risk_level: Optional[str] = None,
    sort: Optional[str] = None,
    order: Optional[str] = None,
    page: int = DEFAULT_PAGE,
    limit: int = DEFAULT_LIMIT,
    flagged_only: bool = False,
) -> StaffListResponse:
    records = get_all_records()
    filtered = filter_faculty(
        records,
        search=search,
        department=department,
        age_range=age_range or "all",
        risk_level=risk_level or "all",
        flagged_only=flagged_only,
    )
    ordered = sort_faculty(filtered, sort=sort or "name", order=order or "asc")
    items_slice, total = paginate(ordered, page=page, limit=limit)
    return StaffListResponse(
        items=[StaffRecord(**normalize_record(r)) for r in items_slice],
        total=total,
        page=page,
        limit=limit,
    )


def _query_dict_faculty(
    search, department, ageRange, riskLevel, sort, order, page, limit
) -> dict:
    q = {"sort": sort, "order": order, "page": page, "limit": limit}
    if search is not None:
        q["search"] = search
    if department:
        q["department"] = list(department)
    if ageRange is not None:
        q["ageRange"] = ageRange
    if riskLevel is not None:
        q["riskLevel"] = riskLevel
    return q


@router.get("", response_model=StaffListResponse)
async def list_faculty(
    search: Optional[str] = Query(None),
    department: Optional[List[str]] = Query(None),
    ageRange: Optional[str] = Query(None, alias="ageRange"),
    riskLevel: Optional[str] = Query(None, alias="riskLevel"),
    sort: Optional[str] = Query("name"),
    order: Optional[str] = Query("asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=500),
):
    """Summary/Faculty Directory: paginated, filterable, sortable faculty list."""
    query = _query_dict_faculty(search, department, ageRange, riskLevel, sort, order, page, limit)
    cached = get_cached(_API_PATH_FACULTY, query)
    if cached is not None:
        return cached
    resp = _list_response(
        search=search,
        department=department,
        age_range=ageRange,
        risk_level=riskLevel,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
        flagged_only=False,
    )
    set_cached(_API_PATH_FACULTY, query, resp.model_dump(mode="json"))
    return resp


@router.get("/flagged", response_model=StaffListResponse)
async def list_flagged(
    riskLevel: Optional[str] = Query(None, alias="riskLevel"),
    department: Optional[List[str]] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=500),
):
    """Flagged & Critical: faculty with status Critical or High Risk."""
    query = {"page": page, "limit": limit}
    if riskLevel is not None:
        query["riskLevel"] = riskLevel
    if department:
        query["department"] = list(department)
    if search is not None:
        query["search"] = search
    cached = get_cached(_API_PATH_FACULTY_FLAGGED, query)
    if cached is not None:
        return cached
    resp = _list_response(
        search=search,
        department=department,
        age_range=None,
        risk_level=riskLevel,
        sort="name",
        order="asc",
        page=page,
        limit=limit,
        flagged_only=True,
    )
    set_cached(_API_PATH_FACULTY_FLAGGED, query, resp.model_dump(mode="json"))
    return resp


@router.get("/export")
async def export_faculty(
    search: Optional[str] = Query(None),
    department: Optional[List[str]] = Query(None),
    ageRange: Optional[str] = Query(None, alias="ageRange"),
    riskLevel: Optional[str] = Query(None, alias="riskLevel"),
    sort: Optional[str] = Query("name"),
    order: Optional[str] = Query("asc"),
    format: Optional[str] = Query("csv", alias="format"),
):
    """Export faculty list as CSV or Excel (same filters as list, no pagination)."""
    resp = _list_response(
        search=search,
        department=department,
        age_range=ageRange,
        risk_level=riskLevel,
        sort=sort,
        order=order,
        page=1,
        limit=10000,
        flagged_only=False,
    )
    rows = []
    for r in resp.items:
        rows.append({
            "id": r.id,
            "employee_id": r.employee_id,
            "name": r.name,
            "age": r.age,
            "gender": r.gender,
            "department": r.department,
            "screening_date": r.screening_date,
            "health_score": r.health_score,
            "status": r.status,
            "active_flags": ", ".join(r.active_flags) if r.active_flags else "",
            "inference": r.inference or "",
            "suggestion": ", ".join(r.suggestion) if r.suggestion else "",
        })

    if (format or "").lower() == "xlsx":
        import pandas as pd
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Faculty", index=False)
        output.seek(0)
        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="faculty-export.xlsx"'},
        )

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="faculty-export.csv"'},
    )


@router.get("/export-csv")
async def export_faculty_health_summary_csv(
    search: Optional[str] = Query(None),
    department: Optional[List[str]] = Query(None),
    ageRange: Optional[str] = Query(None, alias="ageRange"),
    riskLevel: Optional[str] = Query(None, alias="riskLevel"),
    sort: Optional[str] = Query("name"),
    order: Optional[str] = Query("asc"),
):
    """
    Faculty Health Summary: Export CSV

    GET /api/faculty/export-csv
    Returns a flat CSV with one row per staff, matching the filters.
    """
    resp = _list_response(
        search=search,
        department=department,
        age_range=ageRange,
        risk_level=riskLevel,
        sort=sort,
        order=order,
        page=1,
        limit=10000,
        flagged_only=False,
    )

    rows = []
    for r in resp.items:
        rows.append(
            {
                "Employee ID": r.employee_id,
                "Name": r.name,
                "Department": r.department,
                "Age": r.age,
                "Gender": r.gender,
                "Health Score": r.health_score,
                "Risk Level": r.status,
                "Last Assessment Date": r.screening_date,
                "Primary Flagged Conditions": ", ".join(r.active_flags) if r.active_flags else "",
            }
        )

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="faculty_health_summary.csv"'},
    )


@router.get("/download-all-reports")
async def download_all_faculty_reports(
    search: Optional[str] = Query(None),
    department: Optional[List[str]] = Query(None),
    ageRange: Optional[str] = Query(None, alias="ageRange"),
    riskLevel: Optional[str] = Query(None, alias="riskLevel"),
    sort: Optional[str] = Query("name"),
    order: Optional[str] = Query("asc"),
):
    """
    Faculty Health Summary: Download All Staff Reports (Excel)

    GET /api/faculty/download-all-reports
    Generates a multi-sheet Excel workbook with summary, labs, clinical findings, and inferences.
    """
    import pandas as pd

    resp = _list_response(
        search=search,
        department=department,
        age_range=ageRange,
        risk_level=riskLevel,
        sort=sort,
        order=order,
        page=1,
        limit=10000,
        flagged_only=False,
    )

    # Sheet 1: Summary
    summary_rows = []
    for r in resp.items:
        summary_rows.append(
            {
                "ID": r.id,
                "Name": r.name,
                "Risk Level": r.status,
                "Overall Score": r.health_score,
                "Department": r.department,
            }
        )

    # Sheet 2: Laboratory Data (flatten Thyrocare panels)
    lab_rows = []
    for r in resp.items:
        tc = r.thyrocare_results or {}
        for panel_name, tests in tc.items():
            if not isinstance(tests, list):
                continue
            for test in tests:
                name = test.get("name") if isinstance(test, dict) else None
                value = test.get("value") if isinstance(test, dict) else None
                unit = test.get("unit") if isinstance(test, dict) else None
                ref_range = test.get("ref_range") if isinstance(test, dict) else None
                status = test.get("status") if isinstance(test, dict) else None
                lab_rows.append(
                    {
                        "Employee ID": r.employee_id,
                        "Name": r.name,
                        "Department": r.department,
                        "Test Group": panel_name,
                        "Test Name": name,
                        "Value": value,
                        "Unit": unit,
                        "Reference Range": ref_range,
                        "Status": status,
                    }
                )

    # Sheet 3: Clinical Findings (SecondMedic results)
    clinical_rows = []
    for r in resp.items:
        sm = r.secondmedic_results or {}
        for modality, fi in sm.items():
            findings = None
            impression = None
            if isinstance(fi, dict):
                findings = fi.get("findings")
                impression = fi.get("impression")
            clinical_rows.append(
                {
                    "Employee ID": r.employee_id,
                    "Name": r.name,
                    "Department": r.department,
                    "Modality": modality,
                    "Findings": findings,
                    "Impression": impression,
                }
            )

    # Sheet 4: Inferences
    inference_rows = []
    for r in resp.items:
        inference_rows.append(
            {
                "Employee ID": r.employee_id,
                "Name": r.name,
                "Department": r.department,
                "Risk Level": r.status,
                "Overall Score": r.health_score,
                "Inference": r.inference or "",
                "Suggestions": ", ".join(r.suggestion) if r.suggestion else "",
            }
        )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)
        pd.DataFrame(lab_rows).to_excel(writer, sheet_name="Laboratory Data", index=False)
        pd.DataFrame(clinical_rows).to_excel(writer, sheet_name="Clinical Findings", index=False)
        pd.DataFrame(inference_rows).to_excel(writer, sheet_name="Inferences", index=False)

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="faculty_health_reports_all_staff.xlsx"'
        },
    )


@router.get("/{id}", response_model=StaffRecord)
async def get_faculty_by_id(id: str = Path(..., alias="id")):
    """Faculty profile: single staff by id. Returns 404 if not found."""
    path = f"{_API_PATH_FACULTY_ID}/{id}"
    cached = get_cached(path, {})
    if cached is not None:
        return cached
    records = get_all_records()
    for r in records:
        if str(r.get("id")) == str(id):
            staff = StaffRecord(**normalize_record(r))
            set_cached(path, {}, staff.model_dump(mode="json"))
            return staff
    raise HTTPException(status_code=404, detail="Staff not found")


@router.get("/{id}/download-pdf")
async def download_faculty_pdf(id: str = Path(..., alias="id")):
    """
    Download individual faculty health summary as a PDF.
    """
    # Reuse the same data source and normalization logic as the JSON profile
    records = get_all_records()
    staff_record: Optional[StaffRecord] = None
    for r in records:
        if str(r.get("id")) == str(id):
            staff_record = StaffRecord(**normalize_record(r))
            break

    if staff_record is None:
        raise HTTPException(status_code=404, detail="Staff not found")

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Simple one-page summary layout
    x_margin = 40
    y = height - 50

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(x_margin, y, "Faculty Health Summary")
    y -= 30

    pdf.setFont("Helvetica", 11)

    def line(text: str):
        nonlocal y
        pdf.drawString(x_margin, y, text)
        y -= 18
        if y < 60:
            pdf.showPage()
            pdf.setFont("Helvetica", 11)
            y = height - 50

    line(f"Name: {staff_record.name}")
    line(f"Employee ID: {staff_record.employee_id}")
    line(f"Department: {staff_record.department}")
    line(f"Age / Gender: {staff_record.age} / {staff_record.gender}")
    line(f"Screening Date: {staff_record.screening_date}")
    line("")
    line(f"Health Score: {staff_record.health_score}")
    line(f"Risk Level: {staff_record.status}")
    flags_text = ", ".join(staff_record.active_flags) if staff_record.active_flags else "None"
    line(f"Primary Flagged Conditions: {flags_text}")
    line("")

    # --- Laboratory Data (Thyrocare) ---
    tc = staff_record.thyrocare_results or {}
    if tc:
        line("Laboratory Data")
        pdf.setFont("Helvetica-Bold", 11)
        line("Panels and Key Tests:")
        pdf.setFont("Helvetica", 10)
        max_width = width - 2 * x_margin
        for panel_name, tests in tc.items():
            if not isinstance(tests, list):
                continue
            line(f"- {panel_name}")
            for test in tests:
                if not isinstance(test, dict):
                    continue
                name = str(test.get("name") or "")
                value = test.get("value")
                unit = str(test.get("unit") or "")
                status = str(test.get("status") or "")
                ref_range = str(test.get("ref_range") or "")
                value_str = f"{value} {unit}".strip() if value is not None else unit
                text = f"    {name}: {value_str} (Status: {status}, Ref: {ref_range})"

                # wrap line if needed
                words = text.split()
                current = ""
                for w in words:
                    test_line = (current + " " + w).strip()
                    if pdf.stringWidth(test_line, "Helvetica", 10) > max_width:
                        line(current)
                        current = w
                    else:
                        current = test_line
                if current:
                    line(current)
        pdf.setFont("Helvetica", 11)
        line("")

    # --- Clinical Findings (SecondMedic) ---
    sm = staff_record.secondmedic_results or {}
    if sm:
        line("Clinical Findings")
        pdf.setFont("Helvetica", 10)
        max_width = width - 2 * x_margin
        for modality, fi in sm.items():
            findings = ""
            impression = ""
            if isinstance(fi, dict):
                findings = str(fi.get("findings") or "")
                impression = str(fi.get("impression") or "")
            line(f"- {modality}")
            if findings:
                text = f"    Findings: {findings}"
                words = text.split()
                current = ""
                for w in words:
                    test_line = (current + " " + w).strip()
                    if pdf.stringWidth(test_line, "Helvetica", 10) > max_width:
                        line(current)
                        current = w
                    else:
                        current = test_line
                if current:
                    line(current)
            if impression:
                text = f"    Impression: {impression}"
                words = text.split()
                current = ""
                for w in words:
                    test_line = (current + " " + w).strip()
                    if pdf.stringWidth(test_line, "Helvetica", 10) > max_width:
                        line(current)
                        current = w
                    else:
                        current = test_line
                if current:
                    line(current)
        pdf.setFont("Helvetica", 11)
        line("")

    # --- Inference and Suggested Actions ---
    if staff_record.inference:
        line("Inference:")
        pdf.setFont("Helvetica", 10)
        max_width = width - 2 * x_margin
        words = staff_record.inference.split()
        current = ""
        for w in words:
            test_line = (current + " " + w).strip()
            if pdf.stringWidth(test_line, "Helvetica", 10) > max_width:
                line(current)
                current = w
            else:
                current = test_line
        if current:
            line(current)
        pdf.setFont("Helvetica", 11)
        line("")

    if staff_record.suggestion:
        line("Suggested Actions:")
        pdf.setFont("Helvetica", 10)
        max_width = width - 2 * x_margin
        for s in staff_record.suggestion:
            suggestion_text = f"- {s}"
            words = suggestion_text.split()
            current = ""
            for w in words:
                test_line = (current + " " + w).strip()
                if pdf.stringWidth(test_line, "Helvetica", 10) > max_width:
                    line(current)
                    current = w
                else:
                    current = test_line
            if current:
                line(current)
        pdf.setFont("Helvetica", 11)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"faculty_health_summary_{staff_record.employee_id}.pdf"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }

    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers=headers,
    )

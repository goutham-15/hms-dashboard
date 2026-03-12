"""
GET /api/faculty, /api/faculty/flagged, /api/faculty/export, /api/faculty/:id
"""
import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Query, Path
from fastapi.responses import Response

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


@router.get("/{id}", response_model=StaffRecord)
async def get_faculty_by_id(id: str = Path(..., alias="id")):
    """Faculty profile: single staff by id. Returns 404 if not found."""
    from fastapi import HTTPException
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

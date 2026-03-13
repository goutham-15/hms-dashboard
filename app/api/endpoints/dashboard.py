"""
GET /api/dashboard, /api/dashboard/alerts, /api/dashboard/export
"""
import csv
import io
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.services.faculty_data import (
    get_summary,
    get_stats,
    get_alerts_list,
    get_all_records,
    normalize_record,
)
from app.utils.api_cache import get_cached, set_cached
from app.schema.api_schemas import DashboardData, DashboardSummary, DashboardStats, StaffRecord

router = APIRouter()

_API_PATH_DASHBOARD = "dashboard"
_API_PATH_ALERTS = "dashboard/alerts"


@router.get("", response_model=DashboardData)
async def get_dashboard():
    """Executive summary: KPIs, department bar, pie, age/gender/conditions, scorecard."""
    cached = get_cached(_API_PATH_DASHBOARD, {})
    if cached is not None:
        return cached
    summary = get_summary()
    stats = get_stats()
    data = DashboardData(
        summary=DashboardSummary(**summary),
        stats=DashboardStats(**stats),
    )
    set_cached(_API_PATH_DASHBOARD, {}, data.model_dump(mode="json"))
    return data


@router.get("/alerts", response_model=list[StaffRecord])
async def get_dashboard_alerts(limit: Optional[int] = Query(None, description="Max items")):
    """Alerts strip: high-risk faculty (Critical/High Risk)."""
    query = {} if limit is None else {"limit": limit}
    cached = get_cached(_API_PATH_ALERTS, query)
    if cached is not None:
        return cached
    alerts = get_alerts_list()
    if limit is not None and limit > 0:
        alerts = alerts[:limit]
    items = [StaffRecord(**normalize_record(r)) for r in alerts]
    set_cached(_API_PATH_ALERTS, query, [x.model_dump(mode="json") for x in items])
    return items


@router.get("/export")
async def export_dashboard(
    search: Optional[str] = Query(None, description="Filter by department name"),
    format: Optional[str] = Query("csv", alias="format", description="csv or xlsx"),
):
    """Export department scorecard as CSV or Excel."""
    summary = get_summary()
    stats = get_stats()
    dept_dist = stats.get("department_distribution") or {}

    rows = []
    for dept, counts in dept_dist.items():
        if search and search.strip() and search.strip().lower() not in (dept or "").lower():
            continue
        total = counts.get("total", 0)
        critical = counts.get("Critical", 0)
        high_risk = counts.get("High Risk", 0)
        moderate = counts.get("Moderate Risk", 0)
        healthy = counts.get("Healthy", 0)
        avg_score = summary.get("avg_health_score") or 0
        # Per-dept avg would need to be computed from records; use global for now
        rows.append({
            "Department": dept or "",
            "Faculty Count": total,
            "Critical": critical,
            "High Risk": high_risk,
            "Moderate": moderate,
            "Healthy": healthy,
            "Avg Score": avg_score,
            "Top Risk": "Critical" if critical else ("High Risk" if high_risk else ("Moderate Risk" if moderate else "Healthy")),
            "Screening %": "100" if total else "0",
            "Action": "Review" if (critical or high_risk) else "Monitor",
        })

    if (format or "").lower() == "xlsx":
        import pandas as pd
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Departments", index=False)
        output.seek(0)
        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="departments-export.xlsx"'},
        )

    # CSV
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="departments-export.csv"'},
    )


@router.get("/export-csv")
async def export_dashboard_csv():
    """
    Executive Summary: Export CSV

    GET /api/dashboard/export-csv
    Exports the institutional health scorecard by department.
    """
    summary = get_summary()
    stats = get_stats()
    dept_dist = stats.get("department_distribution") or {}

    rows = []
    for dept, counts in dept_dist.items():
        total = counts.get("total", 0)
        critical = counts.get("Critical", 0)
        high_risk = counts.get("High Risk", 0)
        moderate = counts.get("Moderate Risk", 0)
        healthy = counts.get("Healthy", 0)
        avg_score = summary.get("avg_health_score") or 0
        top_risk = "Critical" if critical else ("High Risk" if high_risk else ("Moderate Risk" if moderate else "Healthy"))
        rows.append(
            {
                "Department": dept or "",
                "Total Faculty": total,
                "Critical Cases": critical,
                "High Risk Cases": high_risk,
                "Moderate Risk Cases": moderate,
                "Healthy Cases": healthy,
                "Average Health Score": avg_score,
                "Top Risk Factor": top_risk,
                "Screening Completion %": "100" if total else "0",
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
        headers={"Content-Disposition": 'attachment; filename="executive_summary_scorecard.csv"'},
    )

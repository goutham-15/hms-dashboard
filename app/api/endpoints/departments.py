from fastapi import APIRouter

from app.api.services.department_stats import (
    build_department_names,
    build_department_stats,
)
from app.api.services.faculty_data import get_all_records, get_stats
from app.schema.api_schemas import DepartmentStats

router = APIRouter()


@router.get("", response_model=list[str])
async def list_departments():
    """List department names for filters/navigation."""
    stats = await get_stats()
    records = await get_all_records()
    return list(build_department_names(stats, records))


@router.get("/stats", response_model=list[DepartmentStats])
async def department_stats():
    """Department-level KPIs for departments page."""
    records = await get_all_records()
    return [
        DepartmentStats(**row).model_dump(mode="json")
        for row in build_department_stats(records)
    ]

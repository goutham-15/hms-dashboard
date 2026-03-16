from fastapi import APIRouter

from app.api.services.department_stats import build_department_comparisons
from app.api.services.faculty_data import get_all_records
from app.schema.api_schemas import DepartmentComparison

router = APIRouter()


@router.get("/departments", response_model=list[DepartmentComparison])
async def compare_departments():
    """Compare departments by health score and risk distribution."""
    records = await get_all_records()
    return [
        DepartmentComparison(**row).model_dump(mode="json")
        for row in build_department_comparisons(records)
    ]

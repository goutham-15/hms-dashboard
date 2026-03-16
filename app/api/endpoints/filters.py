"""
GET /api/filters — List departments, age ranges, and risk levels for filter dropdowns.
Gets available values from DB, stores in Redis, then returns.
"""
from fastapi import APIRouter

from app.utils.api_cache import get_cached, set_cached
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(name="filters")

_API_PATH_FILTERS = "filters"

# Fixed options per BACKEND_API_TASKS.md (filter param values)
AGE_RANGES = ["30-40", "41-50", "51-60", "60+"]
RISK_LEVELS = ["Critical", "High Risk", "Moderate Risk", "Healthy"]


def _load_filters_from_db() -> dict:
    """Load records from DB and derive filter options from available data."""
    from app.db.database import DatabaseManager
    db = DatabaseManager()
    records = db.get_all_records()
    dept_set = set()
    for r in records:
        d = (r.get("department") or "").strip()
        dept_set.add(d if d else "Others")
    departments = sorted(dept_set)
    if not departments:
        departments = ["Others"]
    return {
        "departments": departments,
        "age_ranges": list(AGE_RANGES),
        "risk_levels": list(RISK_LEVELS),
    }


@router.get("")
async def get_filter_options():
    """
    Return options for filter dropdowns. Fetches available data from DB,
    caches result in Redis, then returns. Cache is cleared when data is updated.
    """
    cached = await get_cached(_API_PATH_FILTERS, {})
    if cached is not None:
        return cached

    try:
        data = _load_filters_from_db()
    except Exception as e:
        logger.warning("Filters load from DB failed: %s; returning defaults", e)
        data = {
            "departments": ["Others"],
            "age_ranges": list(AGE_RANGES),
            "risk_levels": list(RISK_LEVELS),
        }
    await set_cached(_API_PATH_FILTERS, {}, data)
    return data

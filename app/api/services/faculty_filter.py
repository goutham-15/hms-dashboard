"""
Filter, sort, and paginate faculty records for GET /api/faculty and GET /api/faculty/flagged.
"""
from typing import Any, Optional

# Status order for riskLevel sort: Critical > High Risk > Moderate Risk > Healthy
STATUS_ORDER = {"Critical": 0, "High Risk": 1, "Moderate Risk": 2, "Healthy": 3}


def _normalize_status(s: Optional[str]) -> str:
    if not s:
        return "Healthy"
    if s.strip().lower() == "moderate":
        return "Moderate Risk"
    return s.strip()


def _age_in_range(age: int, age_range: Optional[str]) -> bool:
    if not age_range or age_range == "all":
        return True
    a = age or 0
    if age_range == "30-40":
        return 30 <= a <= 40
    if age_range == "41-50":
        return 41 <= a <= 50
    if age_range == "51-60":
        return 51 <= a <= 60
    if age_range == "60+":
        return a > 60
    return True


def _matches_search(r: dict[str, Any], search: Optional[str]) -> bool:
    if not search or not search.strip():
        return True
    q = search.strip().lower()
    name = (r.get("name") or "").lower()
    emp = (r.get("employee_id") or "").lower()
    id_ = (r.get("id") or "").lower()
    return q in name or q in emp or q in id_


def _matches_departments(r: dict[str, Any], departments: Optional[list[str]]) -> bool:
    if not departments:
        return True
    dept = (r.get("department") or "").strip()
    return dept in [d.strip() for d in departments if d]


def _matches_risk(r: dict[str, Any], risk_level: Optional[str]) -> bool:
    if not risk_level or risk_level == "all":
        return True
    status = _normalize_status(r.get("status"))
    want = _normalize_status(risk_level)
    return status == want


def filter_faculty(
    records: list[dict[str, Any]],
    *,
    search: Optional[str] = None,
    department: Optional[list[str]] = None,
    age_range: Optional[str] = None,
    risk_level: Optional[str] = None,
    flagged_only: bool = False,
) -> list[dict[str, Any]]:
    """Apply filters. If flagged_only=True, only Critical and High Risk."""
    out = list(records)
    if flagged_only:
        out = [r for r in out if _normalize_status(r.get("status")) in ("Critical", "High Risk")]
    out = [r for r in out if _matches_search(r, search)]
    out = [r for r in out if _matches_departments(r, department)]
    out = [r for r in out if _age_in_range(r.get("age") or 0, age_range)]
    out = [r for r in out if _matches_risk(r, risk_level)]
    return out


def sort_faculty(
    records: list[dict[str, Any]],
    sort: str = "name",
    order: str = "asc",
) -> list[dict[str, Any]]:
    """Sort by sort field and order (asc/desc)."""
    if not records:
        return records
    rev = order.lower() == "desc"
    key = (sort or "name").strip().lower()

    def sort_key(r: dict[str, Any]):
        if key == "name":
            return (r.get("name") or "").lower()
        if key == "age":
            return r.get("age") or 0
        if key == "department":
            return (r.get("department") or "").lower()
        if key == "healthscore":
            return r.get("health_score") or 0
        if key == "risklevel":
            return STATUS_ORDER.get(_normalize_status(r.get("status")), 4)
        return (r.get("name") or "").lower()

    return sorted(records, key=sort_key, reverse=rev)


def paginate(
    records: list[dict[str, Any]],
    page: int = 1,
    limit: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """Return (page_slice, total). page is 1-based."""
    total = len(records)
    page = max(1, page)
    limit = max(1, min(limit, 500))
    start = (page - 1) * limit
    end = start + limit
    return records[start:end], total

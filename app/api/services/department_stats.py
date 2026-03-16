from collections import Counter
from typing import Any, Iterable, Optional


_STATUS_KEYS = ("Critical", "High Risk", "Moderate Risk", "Healthy")


def _normalize_status(status: Optional[str]) -> str:
    if not status:
        return "Healthy"
    s = status.strip()
    if s.lower() == "moderate":
        return "Moderate Risk"
    return s


def _normalize_department(dept: Optional[str]) -> str:
    d = (dept or "").strip()
    return d if d else "Others"


def _department_names(records: Iterable[dict[str, Any]]) -> list[str]:
    names = {_normalize_department(r.get("department")) for r in records}
    if not names:
        return ["Others"]
    return sorted(names)


def build_department_names(
    stats: dict[str, Any],
    records: Iterable[dict[str, Any]],
) -> list[str]:
    dept_dist = stats.get("department_distribution") or {}
    if dept_dist:
        return sorted(dept_dist.keys())
    return _department_names(records)


def build_department_stats(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    all_records = list(records)
    departments = _department_names(all_records)
    out: list[dict[str, Any]] = []
    for dept in departments:
        dept_records = [r for r in all_records if _normalize_department(r.get("department")) == dept]
        total = len(dept_records)
        critical = sum(1 for r in dept_records if _normalize_status(r.get("status")) == "Critical")
        high = sum(1 for r in dept_records if _normalize_status(r.get("status")) == "High Risk")
        moderate = sum(1 for r in dept_records if _normalize_status(r.get("status")) == "Moderate Risk")
        healthy = sum(1 for r in dept_records if _normalize_status(r.get("status")) == "Healthy")
        avg_score = (
            round(sum(float(r.get("health_score") or 0) for r in dept_records) / total, 1)
            if total
            else 0.0
        )
        screening_completed = sum(1 for r in dept_records if (r.get("screening_date") or "").strip())
        screening_rate = round((screening_completed / total) * 100, 1) if total else 0.0
        out.append(
            {
                "department": dept,
                "headcount": total,
                "critical": critical,
                "high_risk": high,
                "moderate": moderate,
                "healthy": healthy,
                "avg_health_score": avg_score,
                "screening_completed": screening_completed,
                "screening_rate": screening_rate,
                "trend": None,
            }
        )
    return out


def build_department_comparisons(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    all_records = list(records)
    departments = _department_names(all_records)
    comparisons: list[dict[str, Any]] = []
    for dept in departments:
        dept_records = [r for r in all_records if _normalize_department(r.get("department")) == dept]
        total = len(dept_records)
        avg_score = (
            round(sum(float(r.get("health_score") or 0) for r in dept_records) / total, 1)
            if total
            else 0.0
        )
        risk_distribution = {
            status: sum(1 for r in dept_records if _normalize_status(r.get("status")) == status)
            for status in _STATUS_KEYS
        }
        flags = [
            flag
            for r in dept_records
            for flag in (r.get("active_flags") or [])
            if isinstance(flag, str) and flag.strip()
        ]
        top_conditions = [
            {"name": name, "count": count}
            for name, count in Counter(flags).most_common(5)
        ]
        comparisons.append(
            {
                "department": dept,
                "avg_health_score": avg_score,
                "risk_distribution": risk_distribution,
                "top_conditions": top_conditions,
            }
        )
    return comparisons

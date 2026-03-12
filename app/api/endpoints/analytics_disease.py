"""
GET /api/analytics/disease — Disease Analytics page aggregates.
"""
from collections import defaultdict
from typing import Any, Optional

from fastapi import APIRouter, Query

from app.api.services.faculty_data import get_all_records
from app.utils.api_cache import get_cached, set_cached

router = APIRouter()

_API_PATH_DISEASE = "analytics/disease"


def _aggregate_disease(records: list[dict], department_filter: Optional[str] = None) -> dict[str, Any]:
    """Build disease analytics from staff thyrocare_results and active_flags."""
    if department_filter and department_filter.strip():
        dept_lower = department_filter.strip().lower()
        records = [r for r in records if (r.get("department") or "").strip().lower() == dept_lower]

    # Categories from active_flags
    categories: dict[str, int] = defaultdict(int)
    for r in records:
        for flag in r.get("active_flags") or []:
            if flag:
                categories[flag] += 1
    disease_categories = [{"name": k, "count": v} for k, v in sorted(categories.items(), key=lambda x: -x[1])]

    def panel_aggregate(panel_key: str) -> dict[str, Any]:
        """Aggregate one thyrocare panel (e.g. diabetes_panel) across all records."""
        test_counts: dict[str, int] = defaultdict(int)
        test_abnormal: dict[str, int] = defaultdict(int)
        for r in records:
            thyro = r.get("thyrocare_results") or {}
            if not isinstance(thyro, dict):
                continue
            panel = thyro.get(panel_key)
            if not isinstance(panel, list):
                continue
            for item in panel:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                test_counts[name] += 1
                status = (item.get("status") or "").strip().lower()
                if status in ("high", "low", "abnormal", "deficient", "insufficient"):
                    test_abnormal[name] += 1
        return {
            "tests": [{"name": k, "count": v, "abnormal": test_abnormal.get(k, 0)} for k, v in sorted(test_counts.items())],
        }

    diabetes = panel_aggregate("diabetes_panel")
    lipids = panel_aggregate("lipid_profile")
    renal = panel_aggregate("renal_kidney")
    vitamins = panel_aggregate("vitamins_hormones")

    # Cardiac: from secondmedic echocardiogram + ecg
    cardiac_findings: list[str] = []
    for r in records:
        second = r.get("secondmedic_results") or {}
        if not isinstance(second, dict):
            continue
        for key in ("echocardiogram", "ecg"):
            obj = second.get(key)
            if isinstance(obj, dict) and (obj.get("findings") or obj.get("impression")):
                cardiac_findings.append((obj.get("findings") or "") + " " + (obj.get("impression") or ""))
    cardiac = {"findings_count": len(cardiac_findings), "sample_findings": cardiac_findings[:5]}

    # Cancer markers: often in liver_function or a dedicated panel; use active_flags containing "cancer" or "marker"
    cancer_related = [c for c in disease_categories if "cancer" in c["name"].lower() or "marker" in c["name"].lower()]
    cancer_markers = cancer_related if cancer_related else []

    return {
        "disease_categories": disease_categories,
        "diabetes": diabetes,
        "cardiac": cardiac,
        "lipids": lipids,
        "renal": renal,
        "vitamins": vitamins,
        "cancer_markers": cancer_markers,
    }


@router.get("/disease")
async def get_disease_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Disease Analytics: aggregated charts (categories, diabetes, cardiac, lipids, renal, vitamins, cancer markers)."""
    query = {} if department is None else {"department": department}
    cached = get_cached(_API_PATH_DISEASE, query)
    if cached is not None:
        return cached
    records = get_all_records()
    data = _aggregate_disease(records, department_filter=department)
    set_cached(_API_PATH_DISEASE, query, data)
    return data

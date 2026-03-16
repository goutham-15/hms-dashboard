"""
GET /api/analytics/disease — Disease Analytics page aggregates.
"""

import re
from collections import defaultdict
from typing import Any, Optional

from fastapi import APIRouter, Query

from app.api.services.faculty_data import get_all_records
from app.utils.api_cache import get_cached, set_cached

router = APIRouter()

_API_PATH_DISEASE_SUMMARY = "analytics/disease-summary"
_API_PATH_DIABETES = "analytics/diabetes"
_API_PATH_CARDIAC = "analytics/cardiac"
_API_PATH_LIPIDS = "analytics/lipids"
_API_PATH_VITAMINS = "analytics/vitamins"
_API_PATH_RENAL = "analytics/renal"
_API_PATH_CANCER = "analytics/cancer-markers"


def _extract_numeric_value(val: Any) -> Optional[float]:
    """Extract float from various types (str, int, float)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        match = re.search(r"(\d+\.?\d*)", val)
        if match:
            return float(match.group(1))
    return None


def _get_test_value(thyro: dict, panel_key: str, test_name: str) -> Optional[float]:
    """Find a test value in a thyrocare panel."""
    panel = thyro.get(panel_key)
    if not isinstance(panel, list):
        return None
    for item in panel:
        if (item.get("name") or "").strip().lower() == test_name.lower():
            return _extract_numeric_value(item.get("value"))
    return None


def _normalize_department(dept: Optional[str]) -> str:
    d = (dept or "").strip()
    return d or "Others"


def _range_label(value: float, buckets: list[dict[str, Any]]) -> Optional[str]:
    for bucket in buckets:
        low = bucket.get("min")
        high = bucket.get("max")
        if low is None and high is None:
            return bucket["range"]
        if low is None and value < high:
            return bucket["range"]
        if high is None and value >= low:
            return bucket["range"]
        if low is not None and high is not None and low <= value < high:
            return bucket["range"]
    return None


@router.get("/disease-summary")
async def get_disease_summary(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Counts and optional trends for major disease flags."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_DISEASE_SUMMARY, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        lower = department.lower()
        records = [r for r in records if (r.get("department") or "").lower() == lower]

    summary = {
        "Cardiac": 0,
        "Diabetes": 0,
        "Renal": 0,
        "Lipids": 0,
        "Vitamins": 0,
        "CRP": 0,
    }

    for r in records:
        flags = [f.lower() for f in (r.get("active_flags") or [])]
        if any(
            key in flag for flag in flags for key in ["cardiac", "heart", "ecg", "echo"]
        ):
            summary["Cardiac"] += 1
        if any(key in flag for flag in flags for key in ["diabetes", "sugar", "hba1c"]):
            summary["Diabetes"] += 1
        if any(key in flag for flag in flags for key in ["renal", "kidney", "egfr"]):
            summary["Renal"] += 1
        if any(
            key in flag for flag in flags for key in ["lipid", "cholesterol", "ldl"]
        ):
            summary["Lipids"] += 1
        if any(key in flag for flag in flags for key in ["vitamin", "b12", "vit d"]):
            summary["Vitamins"] += 1
        thyro = r.get("thyrocare_results") or {}
        for panel_key, panel in thyro.items():
            if not isinstance(panel, list):
                continue
            val = _get_test_value(thyro, panel_key, "C-REACTIVE PROTEIN (CRP)")
            if val is not None and val > 6:
                summary["CRP"] += 1
                break

    total = len(records)
    data = []
    for name, count in summary.items():
        percentage = round((count / total * 100), 1) if total else 0.0
        data.append(
            {"name": name, "count": count, "percentage": percentage, "trend": None}
        )

    await set_cached(_API_PATH_DISEASE_SUMMARY, query, data)
    return data


@router.get("/diabetes")
async def get_diabetes_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """HbA1c distribution for pie and histogram data."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_DIABETES, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        lower = department.lower()
        records = [r for r in records if (r.get("department") or "").lower() == lower]

    buckets = [
        {"range": "Normal (<5.7)", "min": None, "max": 5.7, "status": "Normal"},
        {
            "range": "Pre-Diabetic (5.7-6.4)",
            "min": 5.7,
            "max": 6.5,
            "status": "Pre-Diabetic",
        },
        {"range": "Fair (6.5-8.0)", "min": 6.5, "max": 8.0, "status": "Fair"},
        {"range": "Poor (>8.0)", "min": 8.0, "max": None, "status": "Poor"},
    ]
    counts = {bucket["range"]: 0 for bucket in buckets}

    for r in records:
        thyro = r.get("thyrocare_results") or {}
        hba1c = _get_test_value(thyro, "diabetes_panel", "HBA1C")
        if hba1c is None:
            continue
        label = _range_label(hba1c, buckets)
        if label:
            counts[label] += 1

    distribution = []
    histogram = []
    for bucket in buckets:
        label = bucket["range"]
        count = counts[label]
        distribution.append({"label": label, "count": count, "value": count})
        histogram.append(
            {"range": label, "count": count, "value": count, "status": bucket["status"]}
        )

    data = {"distribution": distribution, "hba1c": histogram}
    await set_cached(_API_PATH_DIABETES, query, data)
    return data


@router.get("/cardiac")
async def get_cardiac_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Cardiac risk stratification per department."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_CARDIAC, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    dept_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"postCABG": 0, "efLow": 0, "efModerate": 0, "lvh": 0, "normal": 0}
    )

    lower_filter = department.lower() if department else None
    for r in records:
        dept = _normalize_department(r.get("department"))
        if lower_filter and dept.lower() != lower_filter:
            continue
        secondmedic = r.get("secondmedic_results") or {}
        echo = secondmedic.get("echocardiogram") or {}
        findings = (
            (echo.get("findings") or "") + " " + (echo.get("impression") or "")
        ).lower()
        if any(term in findings for term in ["cabg", "stent", "revascularization"]):
            dept_stats[dept]["postCABG"] += 1
        if any(term in findings for term in ["lvh", "left ventricular hypertrophy"]):
            dept_stats[dept]["lvh"] += 1
        match = re.search(r"(?:ef|ejection fraction)(?:\s+is)?\s*(\d+)%", findings)
        if match:
            ef = int(match.group(1))
            if ef < 50:
                dept_stats[dept]["efLow"] += 1
            elif ef < 60:
                dept_stats[dept]["efModerate"] += 1
            else:
                dept_stats[dept]["normal"] += 1

    data = []
    for dept, stats in sorted(dept_stats.items(), key=lambda item: item[0]):
        data.append(
            {
                "department": dept,
                "postCABG": stats["postCABG"],
                "efLow": stats["efLow"],
                "efModerate": stats["efModerate"],
                "lvh": stats["lvh"],
                "normal": stats["normal"],
            }
        )

    await set_cached(_API_PATH_CARDIAC, query, data)
    return data


@router.get("/lipids")
async def get_lipids_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Lipid profile overview with TC/LDL/HDL/TG range counts."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_LIPIDS, query)
    if cached is not None:
        return cached

    bucket_defs = {
        "tc": [
            {
                "range": "Desirable (<200)",
                "min": None,
                "max": 200,
                "status": "Desirable",
            },
            {
                "range": "Borderline (200-239)",
                "min": 200,
                "max": 240,
                "status": "Borderline",
            },
            {"range": "High (>=240)", "min": 240, "max": None, "status": "High"},
        ],
        "ldl": [
            {"range": "Optimal (<100)", "min": None, "max": 100, "status": "Optimal"},
            {
                "range": "Above Optimal (100-129)",
                "min": 100,
                "max": 130,
                "status": "Above Optimal",
            },
            {
                "range": "Borderline (130-159)",
                "min": 130,
                "max": 160,
                "status": "Borderline",
            },
            {"range": "High (>=160)", "min": 160, "max": None, "status": "High"},
        ],
        "hdl": [
            {"range": "Low (<40)", "min": None, "max": 40, "status": "Low"},
            {"range": "Normal (40-59)", "min": 40, "max": 60, "status": "Normal"},
            {"range": "High (>=60)", "min": 60, "max": None, "status": "High"},
        ],
        "tg": [
            {"range": "Normal (<150)", "min": None, "max": 150, "status": "Normal"},
            {
                "range": "Borderline (150-199)",
                "min": 150,
                "max": 200,
                "status": "Borderline",
            },
            {"range": "High (200-499)", "min": 200, "max": 500, "status": "High"},
            {
                "range": "Very High (>=500)",
                "min": 500,
                "max": None,
                "status": "Very High",
            },
        ],
    }

    counts = {
        key: {bucket["range"]: 0 for bucket in buckets}
        for key, buckets in bucket_defs.items()
    }

    records = await get_all_records()
    lower_filter = department.lower() if department else None
    for r in records:
        dept = (r.get("department") or "").lower()
        if lower_filter and dept != lower_filter:
            continue
        thyro = r.get("thyrocare_results") or {}
        metrics = {
            "tc": _get_test_value(thyro, "lipid_profile", "TOTAL CHOLESTEROL"),
            "ldl": _get_test_value(thyro, "lipid_profile", "LDL CHOLESTEROL - DIRECT"),
            "hdl": _get_test_value(thyro, "lipid_profile", "HDL CHOLESTEROL - DIRECT"),
            "tg": _get_test_value(thyro, "lipid_profile", "TRIGLYCERIDES"),
        }
        for key, value in metrics.items():
            if value is None:
                continue
            label = _range_label(value, bucket_defs[key])
            if label:
                counts[key][label] += 1

    data = {
        key: [
            {
                "range": bucket["range"],
                "count": counts[key][bucket["range"]],
                "status": bucket["status"],
            }
            for bucket in buckets
        ]
        for key, buckets in bucket_defs.items()
    }

    await set_cached(_API_PATH_LIPIDS, query, data)
    return data


@router.get("/vitamins")
async def get_vitamins_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Vitamin D and B12 deficiency percentages by department."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_VITAMINS, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    dept_stats = defaultdict(
        lambda: {"total": 0, "vit_d_deficient": 0, "vit_b12_deficient": 0}
    )
    lower_filter = department.lower() if department else None

    for r in records:
        dept = _normalize_department(r.get("department"))
        if lower_filter and dept.lower() != lower_filter:
            continue
        dept_stats[dept]["total"] += 1
        thyro = r.get("thyrocare_results") or {}
        vit_d = _get_test_value(thyro, "vitamins_hormones", "25 - OH VITAMIN D (TOTAL)")
        vit_b12 = _get_test_value(thyro, "vitamins_hormones", "VITAMIN B12")
        if vit_d is not None and vit_d < 20:
            dept_stats[dept]["vit_d_deficient"] += 1
        if vit_b12 is not None and vit_b12 < 200:
            dept_stats[dept]["vit_b12_deficient"] += 1

    data = []
    for dept, stats in sorted(dept_stats.items(), key=lambda item: item[0]):
        total = stats["total"] or 1
        data.append(
            {
                "department": dept,
                "vitD": round((stats["vit_d_deficient"] / total) * 100, 1),
                "vitB12": round((stats["vit_b12_deficient"] / total) * 100, 1),
            }
        )

    await set_cached(_API_PATH_VITAMINS, query, data)
    return data


@router.get("/renal")
async def get_renal_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """eGFR stage distribution for renal dashboard."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_RENAL, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        lower = department.lower()
        records = [r for r in records if (r.get("department") or "").lower() == lower]

    stages = [
        ("Stage 1 (>=90)", 90, None, "#2c7bb6"),
        ("Stage 2 (60-89)", 60, 90, "#abd9e9"),
        ("Stage 3 (30-59)", 30, 60, "#fdae61"),
        ("Stage 4 (15-29)", 15, 30, "#f46d43"),
        ("Stage 5 (<15)", None, 15, "#d73027"),
    ]
    counts = {name: 0 for name, *_ in stages}

    for r in records:
        thyro = r.get("thyrocare_results") or {}
        egfr = _get_test_value(
            thyro, "renal_kidney", "EST. GLOMERULAR FILTRATION RATE (eGFR)"
        )
        if egfr is None:
            continue
        for name, low, high, _ in stages:
            if low is None and egfr < high:
                counts[name] += 1
                break
            if high is None and egfr >= low:
                counts[name] += 1
                break
            if low is not None and high is not None and low <= egfr < high:
                counts[name] += 1
                break

    data = [
        {"name": name, "value": counts[name], "color": color}
        for name, _, _, color in stages
    ]

    await set_cached(_API_PATH_RENAL, query, data)
    return data


@router.get("/cancer-markers")
async def get_cancer_markers_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Cancer marker surveillance table."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_CANCER, query)
    if cached is not None:
        return cached

    marker_defs = {
        "AFP": {
            "panel": "liver_function",
            "test_name": "ALPHA FETOPROTEIN (AFP)",
            "ranges": [
                ("normal", None, 10),
                ("borderline", 10, 100),
                ("elevated", 100, 1000),
                ("critical", 1000, None),
            ],
        },
        "PSA": {
            "panel": "others",
            "test_name": "PROSTATE SPECIFIC ANTIGEN (PSA)",
            "ranges": [
                ("normal", None, 4),
                ("borderline", 4, 10),
                ("elevated", 10, 20),
                ("critical", 20, None),
            ],
        },
        "CEA": {
            "panel": "liver_function",
            "test_name": "CARCINOEMBRYONIC ANTIGEN (CEA)",
            "ranges": [
                ("normal", None, 5),
                ("borderline", 5, 10),
                ("elevated", 10, 100),
                ("critical", 100, None),
            ],
        },
        "CA125": {
            "panel": "liver_function",
            "test_name": "CA 125",
            "ranges": [
                ("normal", None, 35),
                ("borderline", 35, 100),
                ("elevated", 100, 500),
                ("critical", 500, None),
            ],
        },
        "CA19-9": {
            "panel": "liver_function",
            "test_name": "CA 19-9",
            "ranges": [
                ("normal", None, 37),
                ("borderline", 37, 100),
                ("elevated", 100, 500),
                ("critical", 500, None),
            ],
        },
    }

    marker_counts = {
        name: {"normal": 0, "borderline": 0, "elevated": 0, "critical": 0}
        for name in marker_defs
    }

    records = await get_all_records()
    lower_filter = department.lower() if department else None

    def _get_marker_bucket(value: float, ranges: list) -> Optional[str]:
        for status, low, high in ranges:
            if low is None and value < high:
                return status
            if high is None and value >= low:
                return status
            if low is not None and high is not None and low <= value < high:
                return status
        return None

    for r in records:
        dept = (r.get("department") or "").lower()
        if lower_filter and dept != lower_filter:
            continue
        thyro = r.get("thyrocare_results") or {}
        for marker_name, defn in marker_defs.items():
            value = _get_test_value(thyro, defn["panel"], defn["test_name"])
            if value is not None:
                bucket = _get_marker_bucket(value, defn["ranges"])
                if bucket:
                    marker_counts[marker_name][bucket] += 1

    data = [
        {
            "marker": name,
            "normal": counts["normal"],
            "borderline": counts["borderline"],
            "elevated": counts["elevated"],
            "critical": counts["critical"],
        }
        for name, counts in marker_counts.items()
    ]

    await set_cached(_API_PATH_CANCER, query, data)
    return data

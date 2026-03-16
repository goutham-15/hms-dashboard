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

_API_PATH_DISEASE = "analytics/disease"
_API_PATH_DISEASE_SUMMARY = "analytics/disease-summary"
_API_PATH_DIABETES = "analytics/diabetes"
_API_PATH_CARDIAC = "analytics/cardiac"
_API_PATH_LIPIDS = "analytics/lipids"
_API_PATH_VITAMINS = "analytics/vitamins"
_API_PATH_RENAL = "analytics/renal"
_API_PATH_CANCER = "analytics/cancer-markers"


async def check_and_refresh_disease_cache(department: Optional[str] = None) -> bool:
    """
    Check if all essential disease analytics caches are available for a given department.
    If any are missing, they will be naturally repopulated by the next endpoint call,
    but this function can be used to ensure they are all present.
    """
    query = {} if department is None else {"department": department}
    paths = [
        _API_PATH_DISEASE_SUMMARY,
        _API_PATH_DIABETES,
        _API_PATH_CARDIAC,
        _API_PATH_LIPIDS,
        _API_PATH_VITAMINS,
        _API_PATH_RENAL,
        _API_PATH_CANCER,
    ]
    
    missing = False
    for path in paths:
        if await get_cached(path, query) is None:
            missing = True
            break
            
    if not missing:
        return True
        
    from app.utils.logger import get_logger
    logger = get_logger(name="analytics_disease")
    logger.info("Some disease analytics cache keys are missing for dept=%s; they will be repopulated.", department)
    return False


def _extract_numeric_value(val: Any) -> Optional[float]:
    """Extract float from various types (str, int, float)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Extract numbers like "12.5" from "12.5 mg/dL"
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


@router.get("/disease-summary")
async def get_disease_summary(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Counts and trends for major conditions."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_DISEASE_SUMMARY, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        records = [r for r in records if (r.get("department") or "").lower() == department.lower()]

    summary = {
        "Cardiac": 0,
        "Diabetes": 0,
        "Renal": 0,
        "Lipids": 0,
        "Vitamins": 0,
        "CRP": 0
    }

    for r in records:
        flags = [f.lower() for f in (r.get("active_flags") or [])]
        if any("cardiac" in f or "heart" in f or "ecg" in f or "echo" in f for f in flags):
            summary["Cardiac"] += 1
        if any("diabetes" in f or "sugar" in f or "hba1c" in f for f in flags):
            summary["Diabetes"] += 1
        if any("renal" in f or "kidney" in f or "egfr" in f for f in flags):
            summary["Renal"] += 1
        if any("lipid" in f or "cholesterol" in f or "ldl" in f for f in flags):
            summary["Lipids"] += 1
        if any("vitamin" in f or "b12" in f or "vit d" in f for f in flags):
            summary["Vitamins"] += 1
        
        # Check CRP specifically in thyrocare results if not in flags
        thyro = r.get("thyrocare_results") or {}
        crp_val = None
        for p_key in thyro.keys():
            if isinstance(thyro[p_key], list):
                val = _get_test_value(thyro, p_key, "C-REACTIVE PROTEIN (CRP)")
                if val is not None:
                    crp_val = val
                    break
        if crp_val and crp_val > 6: # Generic high CRP threshold
            summary["CRP"] += 1

    data = [{"name": k, "count": v} for k, v in summary.items()]
    await set_cached(_API_PATH_DISEASE_SUMMARY, query, data)
    return data


@router.get("/diabetes")
async def get_diabetes_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """HbA1c distribution and counts."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_DIABETES, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        records = [r for r in records if (r.get("department") or "").lower() == department.lower()]

    dist = {"Normal (<5.7)": 0, "Pre-Diabetic (5.7-6.4)": 0, "Fair (6.5-8.0)": 0, "Poor (>8.0)": 0}
    
    for r in records:
        thyro = r.get("thyrocare_results") or {}
        hba1c = _get_test_value(thyro, "diabetes_panel", "HBA1C")
        if hba1c is None:
            continue
        
        if hba1c < 5.7:
            dist["Normal (<5.7)"] += 1
        elif 5.7 <= hba1c <= 6.4:
            dist["Pre-Diabetic (5.7-6.4)"] += 1
        elif 6.5 <= hba1c <= 8.0:
            dist["Fair (6.5-8.0)"] += 1
        else:
            dist["Poor (>8.0)"] += 1

    data = {
        "distribution": [{"name": k, "count": v} for k, v in dist.items()],
        "total_screened": sum(dist.values())
    }
    await set_cached(_API_PATH_DIABETES, query, data)
    return data


@router.get("/cardiac")
async def get_cardiac_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Cardiac stratification (Post-CABG, EF ranges, LVH)."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_CARDIAC, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        records = [r for r in records if (r.get("department") or "").lower() == department.lower()]

    stats = {
        "Post-CABG/Stent": 0,
        "Low EF (<50%)": 0,
        "Normal EF (>=50%)": 0,
        "LVH Detected": 0
    }

    for r in records:
        second = r.get("secondmedic_results") or {}
        echo = second.get("echocardiogram") or {}
        findings = ((echo.get("findings") or "") + " " + (echo.get("impression") or "")).lower()
        
        if any(x in findings for x in ["cabg", "stent", "revascularization"]):
            stats["Post-CABG/Stent"] += 1
        
        if "ef" in findings or "ejection fraction" in findings:
            match = re.search(r"(?:ef|ejection fraction)(?:\s+is)?\s*(\d+)%", findings)
            if match:
                ef = int(match.group(1))
                if ef < 50:
                    stats["Low EF (<50%)"] += 1
                else:
                    stats["Normal EF (>=50%)"] += 1
        
        if any(x in findings for x in ["lvh", "left ventricular hypertrophy"]):
            stats["LVH Detected"] += 1

    data = [{"name": k, "count": v} for k, v in stats.items()]
    await set_cached(_API_PATH_CARDIAC, query, data)
    return data


@router.get("/lipids")
async def get_lipids_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Lipid distribution by range."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_LIPIDS, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        records = [r for r in records if (r.get("department") or "").lower() == department.lower()]

    tc_dist = {"Desirable (<200)": 0, "Borderline (200-239)": 0, "High (>=240)": 0}
    ldl_dist = {"Optimal (<100)": 0, "Above Optimal (100-129)": 0, "Borderline (130-159)": 0, "High (>=160)": 0}
    
    for r in records:
        thyro = r.get("thyrocare_results") or {}
        tc = _get_test_value(thyro, "lipid_profile", "TOTAL CHOLESTEROL")
        ldl = _get_test_value(thyro, "lipid_profile", "LDL CHOLESTEROL - DIRECT")
        
        if tc:
            if tc < 200: tc_dist["Desirable (<200)"] += 1
            elif tc < 240: tc_dist["Borderline (200-239)"] += 1
            else: tc_dist["High (>=240)"] += 1
        
        if ldl:
            if ldl < 100: ldl_dist["Optimal (<100)"] += 1
            elif ldl < 130: ldl_dist["Above Optimal (100-129)"] += 1
            elif ldl < 160: ldl_dist["Borderline (130-159)"] += 1
            else: ldl_dist["High (>=160)"] += 1

    data = {
        "total_cholesterol": [{"name": k, "count": v} for k, v in tc_dist.items()],
        "ldl": [{"name": k, "count": v} for k, v in ldl_dist.items()]
    }
    await set_cached(_API_PATH_LIPIDS, query, data)
    return data


@router.get("/vitamins")
async def get_vitamins_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Vitamin D and B12 deficiency by department."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_VITAMINS, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    dept_stats = defaultdict(lambda: {"total": 0, "vit_d_deficient": 0, "vit_b12_deficient": 0})
    
    for r in records:
        dept = r.get("department") or "Unknown"
        if department and dept.lower() != department.lower():
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
    for dept, s in dept_stats.items():
        data.append({
            "department": dept,
            "vit_d_pct": round((s["vit_d_deficient"] / s["total"] * 100), 1) if s["total"] > 0 else 0,
            "vit_b12_pct": round((s["vit_b12_deficient"] / s["total"] * 100), 1) if s["total"] > 0 else 0,
            "total": s["total"]
        })
    
    await set_cached(_API_PATH_VITAMINS, query, data)
    return data


@router.get("/renal")
async def get_renal_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """eGFR Stages (1-5) distribution."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_RENAL, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        records = [r for r in records if (r.get("department") or "").lower() == department.lower()]

    stages = {"Stage 1 (>=90)": 0, "Stage 2 (60-89)": 0, "Stage 3 (30-59)": 0, "Stage 4 (15-29)": 0, "Stage 5 (<15)": 0}
    for r in records:
        thyro = r.get("thyrocare_results") or {}
        egfr = _get_test_value(thyro, "renal_kidney", "EST. GLOMERULAR FILTRATION RATE (eGFR)")
        if egfr is None:
            continue
        if egfr >= 90: stages["Stage 1 (>=90)"] += 1
        elif egfr >= 60: stages["Stage 2 (60-89)"] += 1
        elif egfr >= 30: stages["Stage 3 (30-59)"] += 1
        elif egfr >= 15: stages["Stage 4 (15-29)"] += 1
        else: stages["Stage 5 (<15)"] += 1

    data = [{"name": k, "count": v} for k, v in stages.items()]
    await set_cached(_API_PATH_RENAL, query, data)
    return data


@router.get("/cancer-markers")
async def get_cancer_markers_analytics(
    department: Optional[str] = Query(None, description="Filter by department"),
):
    """Cancer markers distribution (Normal, Borderline, Elevated, Critical)."""
    query = {} if department is None else {"department": department}
    cached = await get_cached(_API_PATH_CANCER, query)
    if cached is not None:
        return cached

    records = await get_all_records()
    if department:
        records = [r for r in records if (r.get("department") or "").lower() == department.lower()]

    markers = {"Normal": 0, "Borderline": 0, "Elevated": 0, "Critical": 0}
    for r in records:
        thyro = r.get("thyrocare_results") or {}
        psa = _get_test_value(thyro, "others", "PROSTATE SPECIFIC ANTIGEN (PSA)")
        if psa:
            if psa < 4: markers["Normal"] += 1
            elif psa < 10: markers["Borderline"] += 1
            else: markers["Elevated"] += 1
            continue
        flags = [f.lower() for f in (r.get("active_flags") or [])]
        if any("cancer" in f or "marker" in f or "tumor" in f for f in flags):
            if "critical" in r.get("status", "").lower():
                markers["Critical"] += 1
            elif "high risk" in r.get("status", "").lower():
                markers["Elevated"] += 1
            else:
                markers["Borderline"] += 1

    data = [{"name": k, "count": v} for k, v in markers.items()]
    await set_cached(_API_PATH_CANCER, query, data)
    return data

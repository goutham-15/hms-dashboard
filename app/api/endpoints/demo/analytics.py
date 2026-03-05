import json
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
import os
import pandas as pd
import io

from app.db.database import DatabaseManager
from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(name="analytics")

DEMO_FILE = "demo_records.jsonl"

# Lazy-load DB and Redis clients to avoid startup crashes
_db_manager = None
_redis_client = None

def get_db_manager():
    """Get or create DatabaseManager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager

def get_redis_client():
    """Get or create RedisClient instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client

def load_demo_data():
    """Load demo data from JSONL file (fallback)."""
    if not os.path.exists(DEMO_FILE):
        return []
    records = []
    with open(DEMO_FILE, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def get_data_from_cache_or_db():
    """
    Fetch data with cache-aside pattern:
    1. Check Redis cache first
    2. If cache miss, fetch from database
    3. Store in cache for next time
    """
    cache_key = "analytics:all_records"
    redis_client = get_redis_client()
    
    # Try cache first
    cached_data = redis_client.get(cache_key)
    if cached_data:
        return cached_data
    
    # Cache miss - fetch from database
    logger.info("Fetching data from database")
    try:
        db_manager = get_db_manager()
        data = db_manager.get_all_records()
        
        # If DB is empty, fallback to demo data
        if not data:
            logger.warning("No data in database, using demo data")
            data = load_demo_data()
        
        # Store in cache
        redis_client.set(cache_key, data)
        return data
    except Exception as e:
        logger.error(f"Database fetch failed: {e}, falling back to demo data")
        return load_demo_data()

@router.get("/summary")
async def get_summary():
    """Get summary statistics with caching."""
    cache_key = "analytics:summary"
    redis_client = get_redis_client()
    
    # Check cache first
    cached = redis_client.get(cache_key)
    if cached:
        return cached
    
    # Cache miss - compute from data
    data = get_data_from_cache_or_db()
    total = len(data)
    critical = sum(1 for r in data if r["status"] == "Critical")
    high = sum(1 for r in data if r["status"] == "High Risk")
    moderate = sum(1 for r in data if r["status"] == "Moderate Risk")
    healthy = sum(1 for r in data if r["status"] == "Healthy")
    avg_score = sum(r.get("health_score", 0) for r in data) / total if total > 0 else 0
    
    result = {
        "total_faculty": total,
        "critical": critical,
        "high_risk": high,
        "moderate": moderate,
        "healthy": healthy,
        "avg_health_score": round(avg_score, 1)
    }
    
    # Store in cache
    redis_client.set(cache_key, result)
    return result

@router.get("/stats")
async def get_stats():
    """Get detailed statistics with caching."""
    cache_key = "analytics:stats"
    redis_client = get_redis_client()
    
    # Check cache first
    cached = redis_client.get(cache_key)
    if cached:
        return cached
    
    # Cache miss - compute from data
    data = get_data_from_cache_or_db()
    
    # Donut Chart
    status_counts = {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}
    for r in data:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
        
    # Age Risk
    age_groups = {"30-40": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}, 
                  "41-50": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0},
                  "51-60": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0},
                  "60+": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}}
    
    for r in data:
        age = r["age"]
        if 30 <= age <= 40: group = "30-40"
        elif 41 <= age <= 50: group = "41-50"
        elif 51 <= age <= 60: group = "51-60"
        else: group = "60+"
        
        status = r["status"]
        if status in age_groups[group]:
            age_groups[group][status] += 1
            
    # Top Flags
    flags = {}
    for r in data:
        for flag in r.get("active_flags", []):
            flags[flag] = flags.get(flag, 0) + 1
    
    sorted_flags = [{"name": k, "count": v} for k, v in sorted(flags.items(), key=lambda item: item[1], reverse=True)]

    # Department Distribution
    depts = {}
    for r in data:
        dept = r["department"]
        if dept not in depts:
            depts[dept] = {"total": 0, "Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}
        depts[dept]["total"] += 1
        depts[dept][r["status"]] += 1

    # Gender Distribution
    gender_stats = {"MALE": {"count": 0, "total_score": 0, "high_risk": 0}, 
                    "FEMALE": {"count": 0, "total_score": 0, "high_risk": 0}}
    for r in data:
        g = r["gender"].upper()
        if g in ["M", "MALE"]: 
            g = "MALE"
        elif g in ["F", "FEMALE"]:
            g = "FEMALE"
            
        if g not in gender_stats: 
            gender_stats[g] = {"count": 0, "total_score": 0, "high_risk": 0}
            
        gender_stats[g]["count"] += 1
        gender_stats[g]["total_score"] += r.get("health_score", 0)
        if r["status"] in ["Critical", "High Risk"]:
            gender_stats[g]["high_risk"] += 1

    result = {
        "status_distribution": status_counts,
        "age_risk": age_groups,
        "top_conditions": sorted_flags[:5],
        "department_distribution": depts,
        "gender_comparison": gender_stats
    }
    
    # Store in cache
    redis_client.set(cache_key, result)
    return result

@router.get("/alerts")
async def get_alerts():
    """Get critical alerts with caching."""
    cache_key = "analytics:alerts"
    redis_client = get_redis_client()
    
    # Check cache first
    cached = redis_client.get(cache_key)
    if cached:
        return cached
    
    # Cache miss - compute from data
    data = get_data_from_cache_or_db()
    alerts = [r for r in data if r["status"] in ["Critical", "High Risk"]]
    result = alerts[:5]
    
    # Store in cache
    redis_client.set(cache_key, result)
    return result

@router.get("/records")
async def get_records(query: Optional[str] = None):
    """Get all records or search with caching."""
    redis_client = get_redis_client()
    
    if query:
        # Search with cache
        cache_key = f"analytics:search:{query.lower()}"
        cached = redis_client.get(cache_key)
        if cached:
            return cached
        
        # Cache miss - search in DB or fallback
        try:
            db_manager = get_db_manager()
            data = db_manager.search_records(query)
            if not data:
                # Fallback to demo data search
                all_data = load_demo_data()
                query_lower = query.lower()
                data = [r for r in all_data if query_lower in r["name"].lower() or 
                       query_lower in r["employee_id"].lower() or 
                       query_lower in r["department"].lower()]
        except Exception as e:
            logger.error(f"Search failed: {e}, using demo data")
            all_data = load_demo_data()
            query_lower = query.lower()
            data = [r for r in all_data if query_lower in r["name"].lower() or 
                   query_lower in r["employee_id"].lower() or 
                   query_lower in r["department"].lower()]
        
        # Store in cache with shorter TTL for searches
        redis_client.set(cache_key, data, ttl=1800)
        return data
    else:
        # Return all records (uses main cache)
        return get_data_from_cache_or_db()

@router.get("/export")
async def export_excel():
    """Export data to Excel (always fresh data, no caching)."""
    data = get_data_from_cache_or_db()
    if not data:
        return {"error": "No data available"}
    
    # 1. Sheet 1: Staff Details
    staff_df = pd.DataFrame(data)
    # Cleanup for Excel
    staff_df['active_flags'] = staff_df['active_flags'].apply(lambda x: ", ".join(x) if isinstance(x, list) else "")
    staff_cols = ['employee_id', 'name', 'age', 'gender', 'department', 'screening_date', 'health_score', 'status', 'active_flags', 'inference']
    # Ensure columns exist before selecting
    existing_cols = [c for c in staff_cols if c in staff_df.columns]
    staff_df = staff_df[existing_cols]
    
    # 2. Sheet 2: Department Summary
    dept_stats = []
    depts = sorted(list(set(r.get('department', 'General') for r in data)))
    for dept in depts:
        dept_data = [r for r in data if r.get('department', 'General') == dept]
        total = len(dept_data)
        critical = sum(1 for r in dept_data if r.get('status') == 'Critical')
        high = sum(1 for r in dept_data if r.get('status') == 'High Risk')
        moderate = sum(1 for r in dept_data if r.get('status') == 'Moderate Risk')
        healthy = sum(1 for r in dept_data if r.get('status') == 'Healthy')
        avg_score = sum(r.get('health_score', 0) for r in dept_data) / total if total > 0 else 0
        
        dept_stats.append({
            "Department": dept,
            "Total Faculty": total,
            "Critical": critical,
            "High Risk": high,
            "Moderate": moderate,
            "Healthy": healthy,
            "Avg Score": round(avg_score, 1)
        })
    dept_df = pd.DataFrame(dept_stats)
    
    # 3. Sheet 3: Overall Summary
    total_faculty = len(data)
    overall_stats = [{
        "Metric": "Total Faculty",
        "Value": total_faculty
    }, {
        "Metric": "Critical Cases",
        "Value": sum(1 for r in data if r.get('status') == 'Critical')
    }, {
        "Metric": "High Risk Cases",
        "Value": sum(1 for r in data if r.get('status') == 'High Risk')
    }, {
        "Metric": "Moderate Risk Cases",
        "Value": sum(1 for r in data if r.get('status') == 'Moderate Risk')
    }, {
        "Metric": "Healthy Faculty",
        "Value": sum(1 for r in data if r.get('status') == 'Healthy')
    }, {
        "Metric": "Average Institution Health Score",
        "Value": round(sum(r.get('health_score', 0) for r in data) / total_faculty, 1) if total_faculty > 0 else 0
    }]
    overall_df = pd.DataFrame(overall_stats)

    # 4. Sheet 4: Detailed Medical Results
    medical_records = []
    for r in data:
        eid = r.get('employee_id')
        name = r.get('name')
        
        # Thyrocare (Lab Tests)
        thyrocare = r.get('thyrocare_results', {})
        for category, tests in thyrocare.items():
            for t in tests:
                medical_records.append({
                    "Employee ID": eid,
                    "Name": name,
                    "Type": "Lab Test",
                    "Category": category.replace('_', ' ').title(),
                    "Test/Procedure": t.get('name'),
                    "Result": t.get('value'),
                    "Unit": t.get('unit'),
                    "Ref Range": t.get('ref_range'),
                    "Status": t.get('status'),
                    "Findings/Impression": ""
                })
        
        # SecondMedic (Imaging)
        secondmedic = r.get('secondmedic_results', {})
        for category, res in secondmedic.items():
            if res and (res.get('findings') or res.get('impression')):
                medical_records.append({
                    "Employee ID": eid,
                    "Name": name,
                    "Type": "Imaging/Diagnostic",
                    "Category": category.replace('_', ' ').upper(),
                    "Test/Procedure": category.replace('_', ' ').title(),
                    "Result": "",
                    "Unit": "",
                    "Ref Range": "",
                    "Status": "",
                    "Findings/Impression": f"FINDINGS: {res.get('findings', '')} | IMPRESSION: {res.get('impression', '')}"
                })
    
    medical_df = pd.DataFrame(medical_records)

    # Generate Excel in Memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        staff_df.to_excel(writer, sheet_name='Staff Details', index=False)
        dept_df.to_excel(writer, sheet_name='Department Summary', index=False)
        overall_df.to_excel(writer, sheet_name='Overall Summary', index=False)
        medical_df.to_excel(writer, sheet_name='Detailed Medical Results', index=False)
    
    output.seek(0)
    
    filename = f"Health_Report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

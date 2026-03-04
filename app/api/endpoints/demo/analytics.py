import json
from fastapi import APIRouter, Query
from typing import List, Optional
import os

router = APIRouter()

DEMO_FILE = "demo_records.jsonl"

def load_demo_data():
    if not os.path.exists(DEMO_FILE):
        return []
    records = []
    with open(DEMO_FILE, "r") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

@router.get("/summary")
async def get_summary():
    data = load_demo_data()
    total = len(data)
    critical = sum(1 for r in data if r["status"] == "Critical")
    high = sum(1 for r in data if r["status"] == "High Risk")
    moderate = sum(1 for r in data if r["status"] == "Moderate Risk")
    healthy = sum(1 for r in data if r["status"] == "Healthy")
    avg_score = sum(r.get("health_score", 0) for r in data) / total if total > 0 else 0
    
    return {
        "total_faculty": total,
        "critical": critical,
        "high_risk": high,
        "moderate": moderate,
        "healthy": healthy,
        "avg_health_score": round(avg_score, 1)
    }

@router.get("/stats")
async def get_stats():
    data = load_demo_data()
    
    # Donut Chart
    status_counts = {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}
    for r in data:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
        
    # Age Risk
    age_groups = {"30-40": {"Critical": 0, "High Risk": 0, "Healthy": 0}, 
                  "41-50": {"Critical": 0, "High Risk": 0, "Healthy": 0},
                  "51-60": {"Critical": 0, "High Risk": 0, "Healthy": 0},
                  "60+": {"Critical": 0, "High Risk": 0, "Healthy": 0}}
    
    for r in data:
        age = r["age"]
        if 30 <= age <= 40: group = "30-40"
        elif 41 <= age <= 50: group = "41-50"
        elif 51 <= age <= 60: group = "51-60"
        else: group = "60+"
        
        status = r["status"]
        if status in age_groups[group]:
            age_groups[group][status] += 1
        elif status == "Moderate Risk": # Map moderate to healthy or high for simple bar? 
            pass # Keep it simple for now
            
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
        if g not in gender_stats: gender_stats[g] = {"count": 0, "total_score": 0, "high_risk": 0}
        gender_stats[g]["count"] += 1
        gender_stats[g]["total_score"] += r.get("health_score", 0)
        if r["status"] in ["Critical", "High Risk"]:
            gender_stats[g]["high_risk"] += 1

    return {
        "status_distribution": status_counts,
        "age_risk": age_groups,
        "top_conditions": sorted_flags[:5],
        "department_distribution": depts,
        "gender_comparison": gender_stats
    }

@router.get("/alerts")
async def get_alerts():
    data = load_demo_data()
    # Filter for Critical and High Risk, sort by date (demo data is small so we just take them)
    alerts = [r for r in data if r["status"] in ["Critical", "High Risk"]]
    return alerts[:5]

@router.get("/records")
async def get_records(query: Optional[str] = None):
    data = load_demo_data()
    if query:
        query = query.lower()
        data = [r for r in data if query in r["name"].lower() or query in r["employee_id"].lower() or query in r["department"].lower()]
    return data

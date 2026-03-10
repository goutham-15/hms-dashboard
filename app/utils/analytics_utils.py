
import json
import os
from app.db.database import DatabaseManager
from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger

logger = get_logger(name="analytics_utils")

def calculate_and_update_cache():
    """
    Main function to compute all analytics data and store in Redis.
    This should be called after every new document upload/ingestion.
    """
    logger.info("Starting proactive analytics cache update...")
    db_manager = DatabaseManager()
    redis_client = RedisClient()
    
    # 1. Fetch All Records
    try:
        data = db_manager.get_all_records()
        if not data:
            logger.warning("No data in DB and no fallback to demo data.")
            return False
    except Exception as e:
        logger.error(f"DB Fetch failed during cache update: {e}")
        return False
        
    if not data:
        logger.warning("No data available to cache.")
        return False

    # Store all records
    redis_client.set("analytics:all_records", data, ttl=0) # ttl=0 means no expiry in some redis versions, or we use a very large number

    # 2. Compute Summary
    total = len(data)
    critical = sum(1 for r in data if r["status"] == "Critical")
    high = sum(1 for r in data if r["status"] == "High Risk")
    moderate = sum(1 for r in data if r["status"] == "Moderate Risk")
    healthy = sum(1 for r in data if r["status"] == "Healthy")
    avg_score = sum(r.get("health_score", 0) for r in data) / total if total > 0 else 0
    
    summary = {
        "total_faculty": total,
        "critical": critical,
        "high_risk": high,
        "moderate": moderate,
        "healthy": healthy,
        "avg_health_score": round(avg_score, 1)
    }
    redis_client.set("analytics:summary", summary, ttl=0)

    # 3. Compute Detailed Stats
    # Status Distribution
    status_counts = {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}
    for r in data:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
        
    # Age Risk
    age_groups = {"30-40": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}, 
                  "41-50": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0},
                  "51-60": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0},
                  "60+": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}}
    
    for r in data:
        age = r.get("age", 0) or 0
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
        dept = r.get("department", "Others") or "Others"
        if dept not in depts:
            depts[dept] = {"total": 0, "Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}
        depts[dept]["total"] += 1
        if r["status"] in depts[dept]:
            depts[dept][r["status"]] += 1

    # Gender Distribution
    gender_stats = {"MALE": {"count": 0, "total_score": 0, "high_risk": 0}, 
                    "FEMALE": {"count": 0, "total_score": 0, "high_risk": 0}}
    for r in data:
        g = str(r.get("gender", "MALE")).upper()
        if g in ["M", "MALE"]: g = "MALE"
        elif g in ["F", "FEMALE"]: g = "FEMALE"
        else: g = "MALE"
            
        if g not in gender_stats: 
            gender_stats[g] = {"count": 0, "total_score": 0, "high_risk": 0}
            
        gender_stats[g]["count"] += 1
        gender_stats[g]["total_score"] += r.get("health_score", 0)
        if r["status"] in ["Critical", "High Risk"]:
            gender_stats[g]["high_risk"] += 1

    stats = {
        "status_distribution": status_counts,
        "age_risk": age_groups,
        "top_conditions": sorted_flags[:5],
        "department_distribution": depts,
        "gender_comparison": gender_stats
    }
    redis_client.set("analytics:stats", stats, ttl=0)

    # 4. Compute Alerts
    alerts = [r for r in data if r["status"] in ["Critical", "High Risk"]]
    redis_client.set("analytics:alerts", alerts[:10], ttl=0)

    logger.info("Proactive analytics cache update complete.")
    return True

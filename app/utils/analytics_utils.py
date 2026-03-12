from app.db.database import DatabaseManager
from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger

logger = get_logger(name="analytics_utils")


def _normalize_records_for_analytics(data: list) -> list:
    """Ensure records have numeric health_score and age for aggregation and JSON serialization."""
    return [
        {
            **r,
            "health_score": float(r.get("health_score") or 0),
            "age": int(r.get("age") or 0),
        }
        for r in data
    ]


def compute_analytics_from_records(data: list) -> tuple[dict, dict, list]:
    """
    From a list of staff records, compute (summary, stats, alerts).
    Used by cache update and by DB fallback when Redis is unavailable.
    """
    if not data:
        return (
            {
                "total_faculty": 0,
                "critical": 0,
                "high_risk": 0,
                "moderate": 0,
                "healthy": 0,
                "avg_health_score": 0.0,
            },
            {
                "status_distribution": {},
                "age_risk": {},
                "top_conditions": [],
                "department_distribution": {},
                "gender_comparison": {},
            },
            [],
        )
    total = len(data)
    critical = sum(1 for r in data if r.get("status") == "Critical")
    high = sum(1 for r in data if r.get("status") == "High Risk")
    moderate = sum(1 for r in data if r.get("status") == "Moderate Risk")
    healthy = sum(1 for r in data if r.get("status") == "Healthy")
    avg_score = sum(r.get("health_score", 0) for r in data) / total if total > 0 else 0
    summary = {
        "total_faculty": total,
        "critical": critical,
        "high_risk": high,
        "moderate": moderate,
        "healthy": healthy,
        "avg_health_score": round(avg_score, 1),
    }
    status_counts = {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}
    for r in data:
        status_counts[r.get("status", "Healthy")] = status_counts.get(r.get("status"), 0) + 1
    age_groups = {
        "30-40": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0},
        "41-50": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0},
        "51-60": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0},
        "60+": {"Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0},
    }
    for r in data:
        age = r.get("age", 0) or 0
        if 30 <= age <= 40:
            group = "30-40"
        elif 41 <= age <= 50:
            group = "41-50"
        elif 51 <= age <= 60:
            group = "51-60"
        else:
            group = "60+"
        status = r.get("status", "Healthy")
        if status in age_groups[group]:
            age_groups[group][status] += 1
    flags = {}
    for r in data:
        for flag in r.get("active_flags") or []:
            flags[flag] = flags.get(flag, 0) + 1
    sorted_flags = [{"name": k, "count": v} for k, v in sorted(flags.items(), key=lambda item: -item[1])]
    depts = {}
    for r in data:
        dept = r.get("department") or "Others"
        if dept not in depts:
            depts[dept] = {"total": 0, "Critical": 0, "High Risk": 0, "Moderate Risk": 0, "Healthy": 0}
        depts[dept]["total"] += 1
        if r.get("status") in depts[dept]:
            depts[dept][r["status"]] += 1
    gender_stats = {"MALE": {"count": 0, "total_score": 0, "high_risk": 0}, "FEMALE": {"count": 0, "total_score": 0, "high_risk": 0}}
    for r in data:
        g = str(r.get("gender", "MALE")).upper()
        if g in ("M", "MALE"):
            g = "MALE"
        elif g in ("F", "FEMALE"):
            g = "FEMALE"
        else:
            g = "MALE"
        if g not in gender_stats:
            gender_stats[g] = {"count": 0, "total_score": 0, "high_risk": 0}
        gender_stats[g]["count"] += 1
        gender_stats[g]["total_score"] += r.get("health_score", 0)
        if r.get("status") in ("Critical", "High Risk"):
            gender_stats[g]["high_risk"] += 1
    stats = {
        "status_distribution": status_counts,
        "age_risk": age_groups,
        "top_conditions": sorted_flags[:5],
        "department_distribution": depts,
        "gender_comparison": gender_stats,
    }
    alerts = [r for r in data if r.get("status") in ("Critical", "High Risk")]
    return summary, stats, alerts[:10]


def calculate_and_update_cache():
    """
    Main function to compute all analytics data and store in Redis.
    This should be called after every new document upload/ingestion.
    Returns True only if all Redis writes succeed; False if DB has no data or Redis is unavailable.
    """
    logger.info("Starting proactive analytics cache update...")
    try:
        db_manager = DatabaseManager()
        redis_client = RedisClient()
    except Exception as e:
        logger.error("Failed to init DB or Redis during cache update: %s", e)
        return False

    # 1. Fetch All Records
    try:
        data = db_manager.get_all_records()
        if not data:
            logger.warning("No data in DB and no fallback to demo data.")
            return False
    except Exception as e:
        logger.error("DB fetch failed during cache update: %s", e)
        return False

    try:
        data = _normalize_records_for_analytics(data)
    except Exception as e:
        logger.error("Failed to normalize records for cache: %s", e)
        return False

    if not redis_client.set("analytics:all_records", data, ttl=0):
        logger.warning("Cache not stored: Redis set failed for analytics:all_records")
        return False

    summary, stats, alerts = compute_analytics_from_records(data)

    if not redis_client.set("analytics:summary", summary, ttl=0):
        logger.warning("Cache not stored: Redis set failed for analytics:summary")
        return False
    if not redis_client.set("analytics:stats", stats, ttl=0):
        logger.warning("Cache not stored: Redis set failed for analytics:stats")
        return False
    if not redis_client.set("analytics:alerts", alerts, ttl=0):
        logger.warning("Cache not stored: Redis set failed for analytics:alerts")
        return False

    logger.info("Proactive analytics cache update complete.")
    try:
        from app.utils.api_cache import clear_api_cache
        clear_api_cache()
    except Exception as e:
        logger.warning("Failed to clear API response cache after analytics update: %s", e)
    return True

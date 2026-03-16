"""
Shared data access for /api dashboard and faculty endpoints.
Uses Redis cache when available; falls back to DB when cache is not stored (e.g. Redis down).
"""
from typing import Any, Callable, Optional

from app.utils.redis_client import RedisClient
from app.utils.analytics_utils import (
    calculate_and_update_cache,
    compute_analytics_from_records,
    _normalize_records_for_analytics,
)
from app.utils.logger import get_logger

logger = get_logger(name="faculty_data")

_redis_client: Optional[RedisClient] = None
_default_summary = {
    "total_faculty": 0,
    "critical": 0,
    "high_risk": 0,
    "moderate": 0,
    "healthy": 0,
    "avg_health_score": 0.0,
}


def get_redis() -> RedisClient:
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


async def check_and_refresh_cache() -> bool:
    """
    Master check: verify if ALL essential dashboard and disease analytics caches
    are available in Redis. If ANY are missing, trigger a full refresh.
    """
    # 1. Core analytics keys (Data Cache)
    core_keys = [
        "analytics:all_records",
        "analytics:summary",
        "analytics:stats",
        "analytics:alerts",
    ]
    
    # 2. Disease analytics keys (API Response Cache)
    # Note: These are stored as "api:analytics:..." by set_cached
    disease_keys = [
        "api:analytics:disease-summary",
        "api:analytics:diabetes",
        "api:analytics:cardiac",
        "api:analytics:lipids",
        "api:analytics:vitamins",
        "api:analytics:renal",
        "api:analytics:cancer-markers",
    ]
    
    try:
        redis_client = get_redis()
        missing = False
        
        # Check core keys
        for k in core_keys:
            if await redis_client.get(k) is None:
                missing = True
                break
        
        # If core is missing, we definitely need a refresh
        if missing:
            logger.info("Core analytics cache missing; triggering full refresh.")
            return await calculate_and_update_cache()

        # Optional: Check disease keys.
        for k in disease_keys:
            if await redis_client.get(k) is None:
                logger.debug("Disease analytics cache key %s is missing; will be lazy-loaded.", k)
                break
                
        return True
    except Exception as e:
        logger.warning("Redis check failed during master cache validation: %s", e)
        return False


async def _get_cached_or_refresh(key: str, default: Any, *, refresh: Callable[[], Any]) -> Any:
    try:
        redis_client = get_redis()
        data = await redis_client.get(key)
        if data is not None:
            return data
    except Exception as e:
        logger.warning("Redis get failed for %s: %s", key, e)
    
    # If we are here, cache is missing or Redis failed.
    # Try to refresh EVERYTHING if this is a main dashboard key.
    if key.startswith("analytics:"):
        logger.info("Cache MISS for %s; checking/refreshing all analytics caches.", key)
        if await check_and_refresh_cache():
            try:
                data = await get_redis().get(key)
                if data is not None:
                    return data
            except Exception:
                pass
    else:
        # Fallback for non-analytics keys
        logger.info("Cache MISS for %s; fetching from DB and populating cache.", key)
        # Note: refresh() might need to be awaited if it's async, 
        # but calculate_and_update_cache is the only one used here currently.
        import asyncio
        if asyncio.iscoroutinefunction(refresh):
            res = await refresh()
        else:
            res = refresh()
            
        if res:
            try:
                data = await get_redis().get(key)
                if data is not None:
                    return data
            except Exception:
                pass
    return default


def _load_from_db() -> Optional[list[dict[str, Any]]]:
    """Load and normalize all records from DB. Returns None on failure."""
    try:
        from app.db.database import DatabaseManager
        db = DatabaseManager()
        raw = db.get_all_records()
        if not raw:
            return []
        return _normalize_records_for_analytics(raw)
    except Exception as e:
        logger.warning("DB fallback load failed: %s", e)
        return None


async def get_all_records() -> list[dict[str, Any]]:
    """Return all staff records (from cache or DB fallback)."""
    data = await _get_cached_or_refresh(
        "analytics:all_records",
        default=[],
        refresh=calculate_and_update_cache,
    )
    if data:
        return data
    # Cache not stored (e.g. Redis down): serve from DB
    fallback = _load_from_db()
    if fallback is not None:
        logger.info("Serving all_records from DB fallback (cache not stored).")
        return fallback
    return []


async def get_summary() -> dict[str, Any]:
    """Return dashboard summary (from cache or DB fallback)."""
    data = await _get_cached_or_refresh(
        "analytics:summary",
        default=_default_summary,
        refresh=calculate_and_update_cache,
    )
    if data and (data.get("total_faculty", 0) > 0 or data != _default_summary):
        return data
    fallback = _load_from_db()
    if fallback is not None:
        summary, _, _ = compute_analytics_from_records(fallback)
        logger.info("Serving summary from DB fallback (cache not stored).")
        return summary
    return _default_summary


async def get_stats() -> dict[str, Any]:
    """Return dashboard stats (from cache or DB fallback)."""
    data = await _get_cached_or_refresh(
        "analytics:stats",
        default={},
        refresh=calculate_and_update_cache,
    )
    if data:
        return data
    fallback = _load_from_db()
    if fallback is not None:
        _, stats, _ = compute_analytics_from_records(fallback)
        logger.info("Serving stats from DB fallback (cache not stored).")
        return stats
    return {}


async def get_alerts_list() -> list[dict[str, Any]]:
    """Return alerts (Critical/High Risk) list from cache or DB fallback."""
    data = await _get_cached_or_refresh(
        "analytics:alerts",
        default=[],
        refresh=calculate_and_update_cache,
    )
    if data:
        return data
    fallback = _load_from_db()
    if fallback is not None:
        _, _, alerts = compute_analytics_from_records(fallback)
        logger.info("Serving alerts from DB fallback (cache not stored).")
        return alerts
    return []


def normalize_record(r: dict[str, Any]) -> dict[str, Any]:
    """Ensure a raw record matches API contract (gender MALE/FEMALE, status, dates, etc.)."""
    out = dict(r)
    g = (r.get("gender") or "MALE")
    if isinstance(g, str):
        g = g.strip().upper()
        if g in ("M", "MALE"):
            out["gender"] = "MALE"
        elif g in ("F", "FEMALE"):
            out["gender"] = "FEMALE"
        else:
            out["gender"] = "MALE"
    s = (r.get("status") or "Healthy").strip()
    if s.lower() == "moderate":
        s = "Moderate Risk"
    if s not in ("Critical", "High Risk", "Moderate Risk", "Healthy"):
        out["status"] = "Healthy"
    else:
        out["status"] = s
    if r.get("screening_date") is None:
        out["screening_date"] = ""
    elif not isinstance(out["screening_date"], str):
        out["screening_date"] = str(out["screening_date"])
    if not isinstance(out.get("active_flags"), list):
        out["active_flags"] = []
    if not isinstance(out.get("suggestion"), list):
        out["suggestion"] = []
    if not isinstance(out.get("thyrocare_results"), dict):
        out["thyrocare_results"] = {}
    if not isinstance(out.get("secondmedic_results"), dict):
        out["secondmedic_results"] = {}
    out.setdefault("inference", "")
    out["health_score"] = float(r.get("health_score") or 0)
    out["age"] = int(r.get("age") or 0)
    out["id"] = str(r.get("id") or "")
    out["employee_id"] = str(r.get("employee_id") or "")
    out["name"] = str(r.get("name") or "")
    out["department"] = str(r.get("department") or "")
    return out

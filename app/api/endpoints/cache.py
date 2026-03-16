from fastapi import APIRouter, HTTPException
from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger
from app.utils.analytics_utils import calculate_and_update_cache
from app.api.services.faculty_data import get_all_records

router = APIRouter()
logger = get_logger(name="cache_api")

# Lazy-load Redis client
_redis_client = None


def get_redis_client():
    """Get or create RedisClient instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


@router.post("/update")
async def update_cache():
    """Store all analytics and API response caches."""
    results = {
        "analytics": {"status": "pending", "keys_stored": 0},
        "api_responses": {"status": "pending", "keys_stored": 0},
    }

    # 1. Update core analytics caches
    try:
        success = await calculate_and_update_cache()
        if success:
            results["analytics"] = {"status": "success", "keys_stored": 4}
        else:
            results["analytics"] = {"status": "failed", "keys_stored": 0}
    except Exception as e:
        logger.error(f"Failed to update analytics cache: {e}")
        results["analytics"] = {"status": "error", "error": str(e)}

    # 2. Update API response caches by calling each endpoint handler
    try:
        from app.api.endpoints import (
            dashboard,
            faculty,
            filters,
            analytics_disease,
        )

        api_keys_stored = 0

        # Dashboard endpoints
        try:
            await dashboard.get_dashboard()
            api_keys_stored += 1
        except Exception as e:
            logger.warning(f"Failed to cache dashboard: {e}")

        try:
            await dashboard.get_dashboard_alerts(limit=10)
            api_keys_stored += 1
        except Exception as e:
            logger.warning(f"Failed to cache alerts: {e}")

        # Faculty endpoints (need to pass Query-compatible values)
        try:
            await faculty.list_faculty(
                search=None,
                department=None,
                ageRange=None,
                riskLevel=None,
                sort="name",
                order="asc",
                page=1,
                limit=10,
            )
            api_keys_stored += 1
        except Exception as e:
            logger.warning(f"Failed to cache faculty list: {e}")

        try:
            await faculty.list_flagged(
                riskLevel=None, department=None, search=None, page=1, limit=10
            )
            api_keys_stored += 1
        except Exception as e:
            logger.warning(f"Failed to cache flagged faculty: {e}")

        # Filters endpoint
        try:
            await filters.get_filter_options()
            api_keys_stored += 1
        except Exception as e:
            logger.warning(f"Failed to cache filters: {e}")

        # Disease analytics endpoints
        disease_endpoints = [
            (analytics_disease.get_disease_summary, None),
            (analytics_disease.get_diabetes_analytics, None),
            (analytics_disease.get_cardiac_analytics, None),
            (analytics_disease.get_lipids_analytics, None),
            (analytics_disease.get_vitamins_analytics, None),
            (analytics_disease.get_renal_analytics, None),
            (analytics_disease.get_cancer_markers_analytics, None),
        ]

        for endpoint, dept in disease_endpoints:
            try:
                await endpoint(department=dept)
                api_keys_stored += 1
            except Exception as e:
                logger.warning(f"Failed to cache {endpoint.__name__}: {e}")

        results["api_responses"] = {"status": "success", "keys_stored": api_keys_stored}

    except Exception as e:
        logger.error(f"Failed to update API response caches: {e}")
        results["api_responses"] = {"status": "error", "error": str(e)}

    # Determine overall status
    overall_success = (
        results["analytics"]["status"] == "success"
        and results["api_responses"]["status"] == "success"
    )

    return {
        "status": "success" if overall_success else "partial",
        "message": "Cache update completed",
        "results": results,
    }


@router.delete("/clear")
async def clear_cache():
    """Clear all analytics and API cache."""
    try:
        redis_client = get_redis_client()
        analytics_count = await redis_client.clear_pattern("analytics:*")
        api_count = await redis_client.clear_pattern("api:*")
        total_count = analytics_count + api_count
        return {
            "status": "success",
            "message": f"Cleared {total_count} cache keys",
            "keys_cleared": total_count,
            "analytics_keys_cleared": analytics_count,
            "api_keys_cleared": api_count,
        }
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {e}")


@router.get("/status")
async def cache_status():
    """Check Redis connection status."""
    try:
        redis_client = get_redis_client()
        is_connected = await redis_client.ping()
        return {
            "status": "connected" if is_connected else "disconnected",
            "redis_available": is_connected,
        }
    except Exception as e:
        logger.error(f"Redis status check failed: {e}")
        return {"status": "error", "redis_available": False, "error": str(e)}

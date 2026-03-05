from fastapi import APIRouter, HTTPException
from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger

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

@router.post("/clear")
async def clear_cache():
    """Clear all analytics cache."""
    try:
        redis_client = get_redis_client()
        count = redis_client.clear_pattern("analytics:*")
        return {
            "status": "success",
            "message": f"Cleared {count} cache keys",
            "keys_cleared": count
        }
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {e}")

@router.get("/status")
async def cache_status():
    """Check Redis connection status."""
    try:
        redis_client = get_redis_client()
        is_connected = redis_client.ping()
        return {
            "status": "connected" if is_connected else "disconnected",
            "redis_available": is_connected
        }
    except Exception as e:
        logger.error(f"Redis status check failed: {e}")
        return {
            "status": "error",
            "redis_available": False,
            "error": str(e)
        }

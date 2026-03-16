"""
Redis cache for GET API responses.
Each GET is stored under a key derived from path + query for easy store/get.
"""
import hashlib
import json
from typing import Any, Optional

from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger

logger = get_logger(name="api_cache")

_KEY_PREFIX = "api:"
_DEFAULT_TTL = 0  # no expiry; invalidate on data change

_redis: Optional[RedisClient] = None


def _redis_client() -> RedisClient:
    global _redis
    if _redis is None:
        _redis = RedisClient()
    return _redis


def _normalize_query(query: dict[str, Any]) -> dict[str, Any]:
    """Sort keys and normalize list params so same params → same key."""
    out = {}
    for k in sorted(query.keys()):
        v = query[k]
        if v is None:
            continue
        if isinstance(v, list):
            out[k] = tuple(sorted(str(x) for x in v))
        else:
            out[k] = v
    return out


def _query_hash(query: dict[str, Any]) -> str:
    """Stable short hash for query dict."""
    if not query:
        return ""
    normalized = _normalize_query(query)
    raw = json.dumps(normalized, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def make_cache_key(path: str, query: Optional[dict[str, Any]] = None) -> str:
    """
    Build Redis key for an API response.
    path: e.g. "dashboard", "dashboard/alerts", "faculty", "faculty/flagged", "faculty/123", "analytics/disease"
    query: optional dict of query params (e.g. {"limit": 5, "page": 1})
    """
    path = (path or "").strip().strip("/").replace("/", ":")
    if not path:
        return f"{_KEY_PREFIX}root"
    qh = _query_hash(query or {})
    if qh:
        return f"{_KEY_PREFIX}{path}:{qh}"
    return f"{_KEY_PREFIX}{path}"


async def get_cached(path: str, query: Optional[dict[str, Any]] = None) -> Optional[Any]:
    """Return cached response dict if present, else None."""
    try:
        key = make_cache_key(path, query)
        value = await _redis_client().get(key)
        if value is not None:
            logger.debug("API cache HIT: %s", key)
            return value
    except Exception as e:
        logger.warning("API cache get failed: %s", e)
    return None


async def set_cached(
    path: str,
    query: Optional[dict[str, Any]] = None,
    data: Any = None,
    ttl: int = _DEFAULT_TTL,
) -> bool:
    """Store API response in Redis. Returns True if stored successfully."""
    if data is None:
        return False
    try:
        key = make_cache_key(path, query)
        ok = await _redis_client().set(key, data, ttl=ttl)
        if ok:
            logger.debug("API cache SET: %s", key)
        return bool(ok)
    except Exception as e:
        logger.warning("API cache set failed: %s", e)
        return False


async def clear_api_cache() -> int:
    """Delete all keys matching api:*. Call after upload or data refresh. Returns count deleted."""
    try:
        n = await _redis_client().clear_pattern(f"{_KEY_PREFIX}*")
        if n:
            logger.info("API cache cleared: %s keys", n)
        return n
    except Exception as e:
        logger.warning("API cache clear failed: %s", e)
        return 0

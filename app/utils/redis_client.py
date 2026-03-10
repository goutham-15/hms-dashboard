import json
import redis
from typing import Optional, Any
from app.utils.config import settings
from app.utils.logger import get_logger

logger = get_logger(name="redis_client")


class RedisClient:
    """Redis client for caching with automatic JSON serialization."""
    
    def __init__(self):
        self.client = redis.Redis(
            host=settings.redis.host,
            port=settings.redis.port,
            db=settings.redis.db,
            decode_responses=True
        )
        self.default_ttl = settings.redis.ttl
        
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache and deserialize JSON."""
        try:
            value = self.client.get(key)
            if value:
                logger.info(f"Cache HIT: {key}")
                return json.loads(value)
            logger.info(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with JSON serialization."""
        try:
            serialized = json.dumps(value)
            ttl = ttl if ttl is not None else self.default_ttl
            
            if ttl > 0:
                self.client.setex(key, ttl, serialized)
                logger.info(f"Cache SET: {key} (TTL: {ttl}s)")
            else:
                self.client.set(key, serialized)
                logger.info(f"Cache SET: {key} (No TTL)")
            return True
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            self.client.delete(key)
            logger.info(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        try:
            keys = self.client.keys(pattern)
            if keys:
                count = self.client.delete(*keys)
                logger.info(f"Cache CLEAR: {pattern} ({count} keys)")
                return count
            return 0
        except Exception as e:
            logger.error(f"Redis CLEAR error for pattern {pattern}: {e}")
            return 0
    
    def ping(self) -> bool:
        """Check if Redis is available."""
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Redis PING failed: {e}")
            return False

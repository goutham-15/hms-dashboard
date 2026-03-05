#!/usr/bin/env python3
"""
Start the FastAPI server with Redis caching enabled.
"""

import uvicorn
from app.utils.config import settings
from app.utils.logger import get_logger

logger = get_logger(name="server")

if __name__ == "__main__":
    logger.info(f"Starting HMS Medical Report API on {settings.api.host}:{settings.api.port}")
    logger.info(f"Redis configured at {settings.redis.host}:{settings.redis.port}")
    
    uvicorn.run(
        "app.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=True,
        log_level="info"
    )


import json
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
import os
import pandas as pd
import io

from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(name="analytics")

# Lazy-load Redis client
_redis_client = None

def get_redis_client():
    """Get or create RedisClient instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client

def get_from_cache(key: str, default_value: any = None):
    """
    Get data strictly from Redis. No DB fallback.
    """
    redis_client = get_redis_client()
    data = redis_client.get(key)
    if data is not None:
        return data
    
    logger.warning(f"Cache MISS for {key}. No data returned as fallback is disabled.")
    return default_value

@router.get("/summary")
async def get_summary():
    """Get summary statistics (Source: Cache only)."""
    return get_from_cache("analytics:summary", default_value={
        "total_faculty": 0, "critical": 0, "high_risk": 0, "moderate": 0, "healthy": 0, "avg_health_score": 0
    })

@router.get("/stats")
async def get_stats():
    """Get detailed statistics (Source: Cache only)."""
    return get_from_cache("analytics:stats", default_value={})

@router.get("/alerts")
async def get_alerts():
    """Get critical alerts (Source: Cache only)."""
    return get_from_cache("analytics:alerts", default_value=[])

@router.get("/records")
async def get_records(query: Optional[str] = None):
    """Get all records or search within cached records."""
    all_records = get_from_cache("analytics:all_records", default_value=[])
    
    if query and all_records:
        # Search by filtering the cached list instead of querying DB
        q = query.lower()
        filtered = [
            r for r in all_records 
            if q in str(r.get("name", "")).lower() or 
               q in str(r.get("employee_id", "")).lower() or
               q in str(r.get("department", "")).lower()
        ]
        return filtered
    
    return all_records

@router.get("/export")
async def export_excel():
    """Export data using the cached records."""
    data = get_from_cache("analytics:all_records", default_value=[])
    if not data:
        return {"error": "No cached data available to export"}
    
    staff_df = pd.DataFrame(data)
    if 'active_flags' in staff_df.columns:
        staff_df['active_flags'] = staff_df['active_flags'].apply(lambda x: ", ".join(x) if isinstance(x, list) else "")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        staff_df.to_excel(writer, sheet_name='Staff Details', index=False)
    
    output.seek(0)
    filename = f"Health_Report_Cache_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

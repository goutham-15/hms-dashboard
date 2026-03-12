
import json
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
import os
import pandas as pd
import io

from app.utils.redis_client import RedisClient
from app.utils.logger import get_logger
from app.utils.analytics_utils import calculate_and_update_cache

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

def get_from_cache_or_db(key: str, default_value: any = None):
    """
    Get data from cache; on miss, fetch from DB, store in cache, then return.
    Ensures data is never missed due to cache being empty.
    """
    redis_client = get_redis_client()
    data = redis_client.get(key)
    if data is not None:
        return data

    logger.info(f"Cache MISS for {key}. Fetching from DB and populating cache.")
    if calculate_and_update_cache():
        data = redis_client.get(key)
        if data is not None:
            return data
    return default_value

@router.get("/summary")
async def get_summary():
    """Get summary statistics (cache with DB fallback on miss)."""
    return get_from_cache_or_db("analytics:summary", default_value={
        "total_faculty": 0, "critical": 0, "high_risk": 0, "moderate": 0, "healthy": 0, "avg_health_score": 0
    })

@router.get("/stats")
async def get_stats():
    """Get detailed statistics (cache with DB fallback on miss)."""
    return get_from_cache_or_db("analytics:stats", default_value={})

@router.get("/alerts")
async def get_alerts():
    """Get critical alerts (cache with DB fallback on miss)."""
    return get_from_cache_or_db("analytics:alerts", default_value=[])

@router.get("/records")
async def get_records(query: Optional[str] = None):
    """Get all records or search within cached records."""
    all_records = get_from_cache_or_db("analytics:all_records", default_value=[])
    
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

@router.get("/record/{record_id}")
async def get_record_by_id(record_id: str):
    """Get a single record by ID (cache with DB fallback on miss)."""
    all_records = get_from_cache_or_db("analytics:all_records", default_value=[])
    
    # Find the record with matching ID
    for record in all_records:
        if str(record.get("id")) == str(record_id):
            return record
    
    # If not found, return error
    logger.warning(f"Record with ID {record_id} not found")
    return {"error": "Record not found", "id": record_id}

@router.get("/export")
async def export_excel():
    """Export data using the cached records."""
    data = get_from_cache_or_db("analytics:all_records", default_value=[])
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

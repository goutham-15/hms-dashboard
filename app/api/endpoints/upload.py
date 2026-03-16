from pathlib import Path
from uuid import uuid4
from typing import Optional, Any

from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from pydantic import BaseModel
from celery.result import AsyncResult

from app.celery_app import celery_app
from app.tasks.upload_tasks import process_pdf_upload_task
from app.utils.logger import get_logger
from app.utils.redis_client import RedisClient


logger = get_logger(name="api_upload")
router = APIRouter()


@router.post("/upload", tags=["Extraction"])
async def extract_upload_pdf(
    file: UploadFile | None = File(None, description="Single PDF file"),
    files: list[UploadFile] | None = File(None, description="Multiple PDF files (folder)"),
):
    """
    Upload one or more PDF medical reports and process into structured JSON.
    Send either:
    - **file**: a single PDF (form field name `file`), or
    - **files**: multiple PDFs (form field name `files`) as a folder batch.
    """
    # Normalize to list of files
    if files:
        to_process = [f for f in files if f.filename]
    elif file:
        to_process = [file]
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'file' (single PDF) or 'files' (multiple PDFs).",
        )

    if not to_process:
        raise HTTPException(status_code=400, detail="No file(s) provided.")

    for f in to_process:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Only PDF files are supported. Got: {f.filename or 'unnamed'}.",
            )

    uploads_dir = Path("logs/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    tasks: list[dict[str, str]] = []
    rc = RedisClient()

    for upload_file in to_process:
        source_id = uuid4().hex[:12]
        pdf_path = uploads_dir / f"{source_id}_{Path(upload_file.filename).name}"

        try:
            content = await upload_file.read()
            with open(pdf_path, "wb") as f:
                f.write(content)
            logger.info("Uploaded file saved: %s (source_id=%s)", pdf_path, source_id)

            async_result = process_pdf_upload_task.delay(
                str(pdf_path),
                upload_file.filename,
                source_id,
            )
            
            # Persistent mapping for filenames - our primary tracking for "ALL" tasks
            await rc.set(f"task_filename:{async_result.id}", upload_file.filename, ttl=3600)

            tasks.append(
                {
                    "task_id": async_result.id,
                    "source_id": source_id,
                    "filename": upload_file.filename,
                }
            )
            logger.info(
                "Enqueued background extraction task: task_id=%s, source_id=%s",
                async_result.id,
                source_id,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(
                "Failed to enqueue processing for PDF %s (source_id=%s): %s",
                upload_file.filename,
                source_id,
                e,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to enqueue PDF for background processing: {e}",
            ) from e

    return {
        "message": "Upload accepted; processing in background.",
        "tasks": tasks,
    }


class BulkStatusRequest(BaseModel):
    task_ids: list[str]


@router.post("/status", tags=["Extraction"])
async def upload_status_bulk(request: BulkStatusRequest):
    """
    Check status for multiple tasks at once.
    Pass a JSON body like: {"task_ids": ["id1", "id2", ...]}
    """
    results = []
    rc = RedisClient()
    for task_id in request.task_ids:
        res = AsyncResult(task_id, app=celery_app)
        filename = await rc.get(f"task_filename:{task_id}")
        
        status_info = {
            "task_id": task_id,
            "state": res.state,
            "ready": res.ready(),
            "successful": res.successful() if res.ready() else None,
            "filename": filename or "unknown"
        }
        if res.failed():
            status_info["error"] = str(res.result) if res.result is not None else "Task failed"
        elif res.successful():
            status_info["result"] = res.result
            
        results.append(status_info)
        
    return {
        "total": len(results),
        "tasks": results
    }


@router.get("/status", tags=["Extraction"])
async def upload_status(task_id: Optional[str] = Query(None, description="Optional: Check a specific task ID")):
    """
    Check status of files. 
    - If **task_id** is provided, returns that specific task.
    - If no **task_id** is provided, returns status of ALL current and recent tasks.
    """
    import redis
    from app.utils.config import settings
    # We use sync redis here for scanning keys efficiently
    r_sync = redis.Redis(host=settings.redis.host, port=settings.redis.port, db=settings.redis.db, decode_responses=True)
    rc_async = RedisClient()

    if task_id:
        result = AsyncResult(task_id, app=celery_app)
        filename = await rc_async.get(f"task_filename:{task_id}")
        
        response = {
            "task_id": task_id,
            "state": result.state,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "filename": filename or "unknown"
        }
            
        if result.failed():
            response["error"] = str(result.result) if result.result is not None else "Task failed"
        elif result.successful():
            response["result"] = result.result
        return response

    # No task_id: Find all tasks we've tracked in Redis via 'task_filename:'
    tasks = []
    filename_keys = r_sync.keys("task_filename:*")
    
    for key in filename_keys:
        tid = key.replace("task_filename:", "")
        filename = r_sync.get(key)
        
        res = AsyncResult(tid, app=celery_app)
        
        # Determine actual state
        # Celery returns PENDING for both truly pending and unknown IDs.
        # But since we found the ID in our task_filename map, it's a real task.
        state = res.state
        
        task_info = {
            "task_id": tid,
            "state": state,
            "filename": filename,
            "ready": res.ready(),
            "successful": res.successful() if res.ready() else None,
        }
        
        # Include result/error if finished
        if res.ready():
            if res.successful():
                task_info["result"] = res.result
            else:
                task_info["error"] = str(res.result) if res.result is not None else "Task failed"
                
        tasks.append(task_info)

    return {
        "total": len(tasks),
        "tasks": tasks
    }

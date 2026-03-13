from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from celery.result import AsyncResult

from app.celery_app import celery_app
from app.tasks.upload_tasks import process_pdf_upload_task
from app.utils.logger import get_logger


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


@router.get("/status/{task_id}", tags=["Extraction"])
def upload_status(task_id: str):
    """
    Check background extraction status for a previously enqueued upload.
    """
    result = AsyncResult(task_id, app=celery_app)

    response: dict[str, object] = {
        "task_id": task_id,
        "state": result.state,
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else None,
    }

    if result.failed():
        err = result.result
        response["error"] = str(err) if err is not None else "Task failed"
    elif result.successful():
        response["result"] = result.result

    return response

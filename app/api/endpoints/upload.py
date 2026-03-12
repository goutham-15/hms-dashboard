from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.chunking import TaggedRecursiveTextChunker
from app.core.document_loader import DocumentLoader
from app.core.llm.extraction import MedicalReportExtractor
from app.core.vector_db import VectorDB
from app.utils.config import settings
from app.utils.logger import get_logger
from app.utils.redis_client import RedisClient
from app.aws.client import AWSClient
from app.db.database import DatabaseManager

logger = get_logger(name="api_upload")
router = APIRouter()

# Initialize Redis client and DB manager
redis_client = RedisClient()
db_manager = DatabaseManager()


def _process_one_pdf(
    file: UploadFile,
    pdf_path: Path,
    aws_client: AWSClient,
    vector_db: VectorDB,
) -> dict[str, Any]:
    """Load, chunk, extract one PDF; upsert to DB. Returns extracted payload."""
    loader = DocumentLoader(pdf_path)
    pages = list(loader.iter_pages_text())
    full_text = "\n\n".join([text for _, text in pages]).strip()

    chunker = TaggedRecursiveTextChunker()
    chunks = list(
        chunker.iter_tagged_chunks(
            pages=pages,
            extra_metadata={"file_name": file.filename},
        )
    )
    source_id = pdf_path.stem.split("_", 1)[0]
    vector_db.add_documents(chunks, source_id=source_id)

    llm = aws_client.bedrock_chat(model_kwargs={"temperature": 0.0})
    extractor = MedicalReportExtractor(llm=llm, vector_db=vector_db)
    extracted = extractor.extract(full_text=full_text, source_id=source_id)
    return extracted


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
    aws_client = AWSClient()
    vector_db = VectorDB(
        persist_directory=settings.vector_db.persist_directory,
        collection_name=settings.vector_db.collection_name,
    )
    results: list[dict[str, Any]] = []

    for upload_file in to_process:
        source_id = uuid4().hex[:12]
        pdf_path = uploads_dir / f"{source_id}_{Path(upload_file.filename).name}"

        try:
            content = await upload_file.read()
            with open(pdf_path, "wb") as f:
                f.write(content)
            logger.info("Uploaded file saved: %s (source_id=%s)", pdf_path, source_id)

            extracted = _process_one_pdf(upload_file, pdf_path, aws_client, vector_db)
            payload = extracted.model_dump(mode="json")
            results.append(payload)
            logger.info("Extraction complete: source_id=%s", source_id)

            try:
                db_manager.upsert_faculty_health_record(extracted, source_id=source_id)
                logger.info("Saved to database: source_id=%s", source_id)
            except Exception as db_error:
                logger.error("Failed to save to database: %s", db_error)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Failed processing PDF %s (source_id=%s): %s", upload_file.filename, source_id, e)
            error_text = str(e)
            if "UnrecognizedClientException" in error_text or "security token included in the request is invalid" in error_text:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "AWS credential validation failed for Bedrock. "
                        "Configure valid credentials via config.yaml or AWS_PROFILE."
                    ),
                ) from e
            if "on-demand throughput" in error_text and "inference profile" in error_text:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Bedrock model invocation requires an inference profile. "
                        "Set aws.bedrock.inference_profile_id in config.yaml."
                    ),
                ) from e
            raise HTTPException(status_code=500, detail=f"Failed to process PDF: {e}") from e

    # Update analytics cache once after all uploads
    try:
        from app.utils.analytics_utils import calculate_and_update_cache
        calculate_and_update_cache()
        logger.info("Analytics cache updated after upload(s)")
    except Exception as cache_err:
        logger.warning("Analytics cache update failed: %s", cache_err)

    # Single file: return same shape as before (one object). Multiple: return list.
    return results[0] if len(results) == 1 else results

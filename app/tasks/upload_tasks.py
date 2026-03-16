from pathlib import Path
from typing import Any

from celery import shared_task

from app.aws.client import AWSClient
from app.core.chunking import TaggedRecursiveTextChunker
from app.core.document_loader import DocumentLoader
from app.core.llm.extraction import MedicalReportExtractor
from app.core.vector_db import VectorDB
from app.db.database import DatabaseManager
from app.utils.analytics_utils import calculate_and_update_cache
from app.utils.config import settings
from app.utils.logger import get_logger


logger = get_logger(name="upload_tasks")
db_manager = DatabaseManager()


@shared_task(
    name="process_pdf_upload",
    bind=True,
    autoretry_for=(),  # No automatic retry for any exception
    max_retries=0,     # Disable retries
    acks_late=False    # Task is acknowledged immediately; if worker crashes, task is not redelivered
)
def process_pdf_upload_task(
    self,
    pdf_path_str: str,
    original_filename: str,
    source_id: str,
) -> dict[str, Any]:
    """
    Celery task to process a single uploaded PDF.

    It will:
    - Load and chunk the PDF
    - Upsert into the vector DB
    - Run LLM extraction
    - Upsert into the relational DB
    - Refresh analytics cache
    """
    pdf_path = Path(pdf_path_str)

    if not pdf_path.exists():
        logger.error("PDF path does not exist: %s", pdf_path)
        return {
            "status": "error",
            "message": f"File not found: {pdf_path}",
            "source_id": source_id,
            "filename": original_filename,
        }

    try:
        loader = DocumentLoader(pdf_path)
        pages = list(loader.iter_pages_text())
        full_text = "\n\n".join([text for _, text in pages]).strip()

        chunker = TaggedRecursiveTextChunker()
        chunks = list(
            chunker.iter_tagged_chunks(
                pages=pages,
                extra_metadata={"file_name": original_filename},
            )
        )

        vector_db = VectorDB(
            persist_directory=settings.vector_db.persist_directory,
            collection_name=settings.vector_db.collection_name,
        )
        vector_db.add_documents(chunks, source_id=source_id)

        aws_client = AWSClient()
        llm = aws_client.bedrock_chat(model_kwargs={"temperature": 0.0})
        extractor = MedicalReportExtractor(llm=llm, vector_db=vector_db)
        extracted = extractor.extract(full_text=full_text, source_id=source_id)
        payload = extracted.model_dump(mode="json")

        # 1. Save to Database (Critical - should fail task if this fails)
        try:
            db_manager.upsert_faculty_health_record(extracted, source_id=source_id)
            logger.info("Saved to database: source_id=%s", source_id)
        except Exception as db_error:
            logger.error("Failed to save to database: %s", db_error)
            # Raise exception so Celery marks task as FAILURE
            raise Exception(f"Database error: {str(db_error)}")

        # 2. Update Cache (Critical - should fail task if this fails)
        try:
            import asyncio
            # calculate_and_update_cache returns True/False
            cache_ok = asyncio.run(calculate_and_update_cache())
            if not cache_ok:
                raise Exception("Cache update returned False (check Redis/DB connection)")
            logger.info("Analytics cache updated after background upload")
        except Exception as cache_err:
            logger.error("Analytics cache update failed: %s", cache_err)
            # Raise exception so Celery marks task as FAILURE
            raise Exception(f"Cache update error: {str(cache_err)}")

        logger.info("Background extraction complete: source_id=%s", source_id)

        return {
            "status": "success",
            "source_id": source_id,
            "filename": original_filename,
            "payload": payload,
        }
    except Exception as e:
        logger.exception(
            "Failed processing PDF %s (source_id=%s): %s",
            original_filename,
            source_id,
            e,
        )
        # Re-raise the exception so Celery marks it as FAILURE
        raise e


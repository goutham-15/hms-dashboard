from pathlib import Path
from uuid import uuid4
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

@router.post("/upload", tags=["Extraction"])
async def extract_upload_pdf(
    file: UploadFile = File(...),
):
    """
    Upload a PDF medical report and process it into structured JSON.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file name.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    source_id = uuid4().hex[:12]
    uploads_dir = Path("logs/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = uploads_dir / f"{source_id}_{Path(file.filename).name}"

    try:
        content = await file.read()
        with open(pdf_path, "wb") as f:
            f.write(content)

        logger.info("Uploaded file saved: %s (source_id=%s)", pdf_path, source_id)

        # 1. Load and process the document
        loader = DocumentLoader(pdf_path)
        pages = list(loader.iter_pages_text(dpi=200))
        full_text = "\n\n".join([text for _, text in pages]).strip()
        
        chunker = TaggedRecursiveTextChunker()
        chunks = list(
            chunker.iter_tagged_chunks(
                pages=pages,
                extra_metadata={"file_name": file.filename},
            )
        )
        
        # 2. Setup LLM and VectorDB
        aws_client = AWSClient()
        llm = aws_client.bedrock_chat(model_kwargs={"temperature": 0.0})
        vector_db = VectorDB(
            persist_directory=settings.vector_db.persist_directory,
            collection_name=settings.vector_db.collection_name,
        )
        vector_db.add_documents(chunks, source_id=source_id)
        
        # 3. Run extraction
        extractor = MedicalReportExtractor(llm=llm, vector_db=vector_db)
        extracted = extractor.extract(full_text=full_text, source_id=source_id)

        payload = extracted.model_dump(mode="json")
        logger.info("Extraction complete: source_id=%s", source_id)
        
        # 4. Save to database
        try:
            db_manager.upsert_faculty_health_record(extracted)
            logger.info("Saved to database: source_id=%s", source_id)
            
            # 5. Invalidate cache since new data was added
            redis_client.clear_pattern("analytics:*")
            logger.info("Cache invalidated after new upload")
        except Exception as db_error:
            logger.error(f"Failed to save to database: {db_error}")
            # Continue even if DB save fails

        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed processing uploaded PDF (source_id=%s): %s", source_id, e)
        error_text = str(e)
        if "UnrecognizedClientException" in error_text or "security token included in the request is invalid" in error_text:
            raise HTTPException(
                status_code=502,
                detail=(
                    "AWS credential validation failed for Bedrock. "
                    "Configure valid credentials via config.yaml (`aws.access_key`/`aws.secret_key`) "
                    "or AWS_PROFILE/default AWS credentials."
                ),
            ) from e
        if "on-demand throughput" in error_text and "inference profile" in error_text:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Bedrock model invocation requires an inference profile. "
                    "Set `aws.bedrock.inference_profile_id` in config.yaml to the profile ID/ARN "
                    "that includes your model, or provide a directly invokable model ID."
                ),
            ) from e
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {e}") from e

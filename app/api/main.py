from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from datetime import datetime
from app.core.extractor import MedicalReportExtractor
from app.utils.config import settings
from app.utils.logger import get_logger


logger = get_logger(name="api")

app = FastAPI(
    title="HMS Medical Report API",
    description="API for processing and extracting medical reports",
    version="1.0.0"
)


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    service: str


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint to verify the API is running.
    """
    logger.info("Health check requested")
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="1.0.0",
        service="HMS Medical Report API"
    )


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "message": "HMS Medical Report API",
        "docs": "/docs",
        "health": "/health"
    }


@app.post("/extract/upload", tags=["Extraction"])
async def extract_upload_pdf(
    file: UploadFile = File(...),
    use_ocr: bool = Form(False),
    ocr_threshold: int = Form(100),
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

        extractor = MedicalReportExtractor(temperature=0.0)
        extracted = extractor.extract_from_pdf(
            pdf_path=pdf_path,
            use_ocr=use_ocr,
            ocr_threshold=ocr_threshold,
        )

        payload = extracted.model_dump(mode="json")
        logger.info("Extraction complete: source_id=%s", source_id)

        return {
            "source_id": source_id,
            "file_name": file.filename,
            "stored_path": str(pdf_path),
            "data": payload,
        }
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

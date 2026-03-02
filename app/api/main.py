from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
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

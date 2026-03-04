from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.api.endpoints import upload
from app.api.endpoints.demo import analytics
from app.utils.logger import get_logger

logger = get_logger(name="api")

app = FastAPI(
    title="HMS Medical Report API",
    description="API for processing and extracting medical reports",
    version="1.0.0"
)

# Setup templates and static files
templates = Jinja2Templates(directory="app/ui/templates")
demo_templates = Jinja2Templates(directory="app/ui/demo/templates")

app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")
app.mount("/demo-static", StaticFiles(directory="app/ui/demo/static"), name="demo-static")

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

@app.get("/", response_class=HTMLResponse, tags=["Root"])
async def root(request: Request):
    """
    Dashboard root endpoint.
    """
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/demo", response_class=HTMLResponse, tags=["Demo"])
async def demo(request: Request):
    """
    Demo dashboard endpoint.
    """
    return demo_templates.TemplateResponse("dashboard.html", {"request": request})

# Include routers
app.include_router(upload.router, prefix="/extract")
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])

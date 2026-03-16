from celery import Celery

from app.utils.config import settings
from app.utils.logger import get_logger


logger = get_logger(name="celery_app")


def _redis_url(db: int) -> str:
    return f"redis://{settings.redis.host}:{settings.redis.port}/{db}"


celery_app = Celery(
    "hms_dashboard",
    broker=_redis_url(settings.redis.db),
    backend=_redis_url(settings.redis.db),
    include=[
        "app.tasks.upload_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,  # Results expire after 1 hour
    # Use solo pool to avoid fork; prevents SIGABRT with sentence-transformers/ChromaDB in workers.
    # Override with: celery -A app.celery_app worker --pool=prefork
    worker_pool="solo",
)


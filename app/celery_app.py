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
)


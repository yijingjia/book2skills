"""
Shared Celery application instance.

Both process_book and generate_skill tasks import from here so the worker
can discover all tasks from a single entry-point:

    celery -A app.tasks.celery_app worker --loglevel=info
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "book2skills",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.process_book",
        "app.tasks.generate_skill",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

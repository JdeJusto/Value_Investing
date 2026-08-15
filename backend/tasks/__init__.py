from celery import Celery

from backend.core.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

celery_app = Celery(
    "value_invest_pro",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["backend.tasks.screener"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)

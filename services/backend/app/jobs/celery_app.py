from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery("clipper", broker=settings.redis_url, include=["app.jobs.tasks"])
celery_app.conf.update(
    task_serializer="json", accept_content=["json"], result_serializer="json",
    task_ignore_result=True, task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, task_default_queue="heavy",
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={"visibility_timeout": settings.job_timeout_seconds + 300},
    task_time_limit=settings.job_timeout_seconds + 60,
    timezone="UTC", enable_utc=True,
)

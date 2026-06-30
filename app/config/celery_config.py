from celery import Celery
from app.config.settings import settings

celery_app = Celery(
    "mindsync",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "send-break-reminders": {
            "task": "app.tasks.tasks.send_break_reminders",
            "schedule": 300.0,
        },
        "update-analytics-cache": {
            "task": "app.tasks.tasks.refresh_analytics_cache",
            "schedule": 600.0,
        },
        "generate-daily-reports": {
            "task": "app.tasks.tasks.generate_daily_reports",
            "schedule": 86400.0,
        },
    },
)

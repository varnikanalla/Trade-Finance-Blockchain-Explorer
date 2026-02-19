from celery import Celery
from celery.schedules import crontab
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "trade_finance",
    broker=REDIS_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["app.workers.integrity_worker"],
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
)

# ─── Beat Schedule (Periodic Tasks) ──────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "integrity-check-every-hour": {
        "task": "app.workers.integrity_worker.run_integrity_check",
        "schedule": crontab(minute=0),        # Every hour at :00
        "options": {"queue": "integrity"},
    },
    "integrity-check-daily-full": {
        "task": "app.workers.integrity_worker.run_full_integrity_check",
        "schedule": crontab(hour=2, minute=0), # Daily at 02:00 UTC
        "options": {"queue": "integrity"},
    },
}

celery_app.conf.task_queues = {
    "integrity": {"exchange": "integrity", "routing_key": "integrity"},
    "default": {"exchange": "default", "routing_key": "default"},
}

"""Celery application configuration and task definitions."""
import os
from celery import Celery
from celery.schedules import crontab

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "sharpsharp_lending",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Lagos",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# ── Periodic Tasks (Celery Beat) ──
celery_app.conf.beat_schedule = {
    # DPD update — runs daily at 1am WAT
    "update-dpd-daily": {
        "task": "app.workers.tasks.update_dpd_all_loans",
        "schedule": crontab(hour=1, minute=0),
    },
    # Collections assignment — runs daily at 6am WAT
    "assign-collections-daily": {
        "task": "app.workers.tasks.assign_collections",
        "schedule": crontab(hour=6, minute=0),
    },
    # Loan ladder promotions — runs daily at 2am WAT
    "check-ladder-promotions": {
        "task": "app.workers.tasks.check_ladder_promotions",
        "schedule": crontab(hour=2, minute=0),
    },
    # Expire old offers — runs every hour
    "expire-offers": {
        "task": "app.workers.tasks.expire_old_offers",
        "schedule": crontab(minute=0),
    },
}

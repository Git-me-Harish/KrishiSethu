"""Celery application configuration.

Configures Celery with Redis as broker and result backend, with per-queue
routing for task prioritization:
- default: general async tasks (notifications, profile updates)
- ml-realtime: user-triggered ML inference (disease ID, voice ASR) — GPU workers
- ml-batch: scheduled ML jobs (NDVI refresh, model retraining) — GPU workers
- external-api: syncs with government / third-party APIs — high concurrency
- notifications: SMS, push, email, voice dispatch — high concurrency

Each queue can have its own worker pool with different scaling characteristics.
"""

from __future__ import annotations

from celery import Celery

from krishisetu.core.config import settings

celery_app = Celery(
    "krishisetu",
    broker=str(settings().REDIS_URL),
    backend=str(settings().REDIS_URL),
    include=[
        "krishisetu.workers.tasks.disease",
        "krishisetu.workers.tasks.weather",
        "krishisetu.workers.tasks.ndvi",
        # Future:
        # "krishisetu.workers.tasks.notifications",
    ],
)

celery_app.conf.update(
    # --- Routing ---
    task_routes={
        "krishisetu.workers.tasks.disease.*": {"queue": "ml-realtime"},
        "krishisetu.workers.tasks.weather.*": {"queue": "external-api"},
        "krishisetu.workers.tasks.ndvi.*": {"queue": "ml-batch"},
        # "krishisetu.workers.tasks.notifications.*": {"queue": "notifications"},
    },
    task_default_queue="default",

    # --- Reliability ---
    task_acks_late=True,  # Acknowledge only after task completes
    task_reject_on_worker_lost=True,  # Re-queue if worker crashes
    worker_prefetch_multiplier=1,  # Don't prefetch — fair distribution

    # --- Timeouts ---
    task_time_limit=300,  # Hard kill after 5 min
    task_soft_time_limit=240,  # Soft limit at 4 min
    task_default_retry_delay=60,  # Wait 1 min before retry
    task_default_max_retries=3,

    # --- Result backend ---
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        "master_name": "krishisetu",
        "visibility_timeout": 3600,
    },

    # --- Serialization ---
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # --- Timezone ---
    timezone="UTC",
    enable_utc=True,

    # --- Beat schedule (periodic tasks) ---
    beat_schedule={
        # Hourly weather sync for all districts with plots
        "sync-weather-hourly": {
            "task": "krishisetu.workers.tasks.weather.sync_all_districts_weather",
            "schedule": 3600,  # Every hour (3600 seconds)
            "options": {"queue": "external-api"},
        },
        # 3-hourly alert check
        "check-alerts-3hourly": {
            "task": "krishisetu.workers.tasks.weather.check_and_dispatch_alerts",
            "schedule": 10800,  # Every 3 hours
            "options": {"queue": "external-api"},
        },
        # Hourly alert expiry cleanup
        "expire-alerts-hourly": {
            "task": "krishisetu.workers.tasks.weather.expire_old_alerts",
            "schedule": 3600,  # Every hour
            "options": {"queue": "default"},
        },
        # Nightly NDVI refresh (2 AM UTC = 7:30 AM IST)
        "refresh-ndvi-daily": {
            "task": "krishisetu.workers.tasks.ndvi.refresh_stale_ndvi",
            "schedule": 86400,  # Every 24 hours
            "options": {"queue": "ml-batch", "max_plots": 100},
        },
    },
)


# Convenience alias
app = celery_app

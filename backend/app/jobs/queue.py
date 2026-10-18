"""Celery transport configured from the backend-only Redis URL."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("codeguard_ai", broker=settings.redis_url.get_secret_value())
celery_app.conf.update(
    broker_connection_timeout=2,
    broker_transport_options={
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
        "retry_on_timeout": False,
    },
    task_default_queue="reviews",
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
    task_ignore_result=True,
    task_publish_retry=False,
    task_send_sent_event=False,
    worker_send_task_events=False,
)

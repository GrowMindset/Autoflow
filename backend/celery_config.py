import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker_url = os.getenv("CELERY_BROKER_URL", redis_url)

celery_app = Celery(
    "autoflow",
    broker=broker_url,
    include=["app.tasks.demo", "app.tasks.execute_workflow"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    task_always_eager=True,
    task_eager_propagates=True,
)

import os
from urllib.parse import urlparse, urlunparse

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
from kombu import Queue

load_dotenv()

def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _with_redis_db(url: str, db_index: int) -> str:
    """
    Return the same redis URL but force the DB index path.
    Example: redis://localhost:6379/0 -> redis://localhost:6379/1
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "rediss"}:
        return url
    return urlunparse(parsed._replace(path=f"/{db_index}"))


redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
broker_url = os.getenv("CELERY_BROKER_URL", redis_url).strip()
result_backend = os.getenv("CELERY_RESULT_BACKEND", _with_redis_db(redis_url, 1)).strip()

WORKFLOW_EXECUTION_QUEUE = os.getenv("CELERY_WORKFLOW_QUEUE", "workflow.executions")
WORKFLOW_NODE_TEST_QUEUE = os.getenv("CELERY_NODE_TEST_QUEUE", "workflow.node_tests")
SYSTEM_QUEUE = os.getenv("CELERY_SYSTEM_QUEUE", "system")
SCHEDULE_SCANNER_TASK = "app.tasks.scheduled_triggers.scan_scheduled_workflows"
SCHEDULE_SCANNER_ENABLED = _env_bool("SCHEDULE_TRIGGER_ENABLED", True)

celery_app = Celery(
    "autoflow",
    broker=broker_url,
    backend=result_backend,
    include=[
        "app.tasks.demo",
        "app.tasks.execute_workflow",
        "app.tasks.scheduled_triggers",
    ],
)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=_env_int("CELERY_BROKER_CONNECTION_MAX_RETRIES", 0),
    broker_pool_limit=_env_int("CELERY_BROKER_POOL_LIMIT", 20),
    broker_heartbeat=_env_int("CELERY_BROKER_HEARTBEAT", 30),
    broker_transport_options={
        "visibility_timeout": _env_int("CELERY_VISIBILITY_TIMEOUT", 60 * 60 * 6),
        "socket_keepalive": True,
        "retry_on_timeout": True,
        "health_check_interval": _env_int("CELERY_REDIS_HEALTH_CHECK_INTERVAL", 30),
    },
    result_backend_transport_options={
        "retry_policy": {
            "timeout": _env_int("CELERY_RESULT_BACKEND_TIMEOUT", 5),
        },
        "health_check_interval": _env_int("CELERY_REDIS_HEALTH_CHECK_INTERVAL", 30),
    },
    redis_socket_connect_timeout=_env_int("CELERY_REDIS_CONNECT_TIMEOUT", 5),
    redis_socket_timeout=_env_int("CELERY_REDIS_SOCKET_TIMEOUT", 30),
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue=WORKFLOW_EXECUTION_QUEUE,
    task_queues=(
        Queue(WORKFLOW_EXECUTION_QUEUE),
        Queue(WORKFLOW_NODE_TEST_QUEUE),
        Queue(SYSTEM_QUEUE),
    ),
    task_routes={
        "app.tasks.execute_workflow.run_execution": {"queue": WORKFLOW_EXECUTION_QUEUE},
        "app.tasks.execute_workflow.run_node_test": {"queue": WORKFLOW_NODE_TEST_QUEUE},
        "app.tasks.demo.ping": {"queue": SYSTEM_QUEUE},
        SCHEDULE_SCANNER_TASK: {"queue": SYSTEM_QUEUE},
    },
    beat_schedule=(
        {
            "scan-scheduled-workflows-every-minute": {
                "task": SCHEDULE_SCANNER_TASK,
                "schedule": crontab(minute="*"),
                "options": {"queue": SYSTEM_QUEUE},
            }
        }
        if SCHEDULE_SCANNER_ENABLED
        else {}
    ),
    task_default_priority=_env_int("CELERY_TASK_DEFAULT_PRIORITY", 5),
    worker_prefetch_multiplier=_env_int("CELERY_WORKER_PREFETCH_MULTIPLIER", 1),
    worker_max_tasks_per_child=_env_int("CELERY_WORKER_MAX_TASKS_PER_CHILD", 100),
    worker_max_memory_per_child=_env_int("CELERY_WORKER_MAX_MEMORY_PER_CHILD", 0),
    worker_disable_rate_limits=_env_bool("CELERY_WORKER_DISABLE_RATE_LIMITS", True),
    worker_send_task_events=_env_bool("CELERY_WORKER_SEND_TASK_EVENTS", True),
    task_send_sent_event=_env_bool("CELERY_TASK_SEND_SENT_EVENT", True),
    task_track_started=_env_bool("CELERY_TASK_TRACK_STARTED", True),
    task_acks_late=_env_bool("CELERY_TASK_ACKS_LATE", True),
    task_acks_on_failure_or_timeout=_env_bool("CELERY_TASK_ACKS_ON_FAILURE_OR_TIMEOUT", True),
    task_reject_on_worker_lost=_env_bool("CELERY_TASK_REJECT_ON_WORKER_LOST", True),
    worker_cancel_long_running_tasks_on_connection_loss=_env_bool(
        "CELERY_CANCEL_LONG_RUNNING_ON_CONN_LOSS", True
    ),
    task_soft_time_limit=_env_int("CELERY_TASK_SOFT_TIME_LIMIT", 60 * 8),
    task_time_limit=_env_int("CELERY_TASK_TIME_LIMIT", 60 * 10),
    task_ignore_result=_env_bool("CELERY_TASK_IGNORE_RESULT", True),
    result_expires=_env_int("CELERY_RESULT_EXPIRES", 60 * 60 * 6),
    task_always_eager=_env_bool("CELERY_TASK_ALWAYS_EAGER", False),
    task_eager_propagates=_env_bool("CELERY_TASK_EAGER_PROPAGATES", True),
)

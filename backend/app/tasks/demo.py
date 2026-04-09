from celery_config import celery_app


@celery_app.task(name="app.tasks.demo.ping")
def ping() -> str:
    return "pong"

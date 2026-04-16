from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.user import User
from app.models.workflows import Workflow
from app.services.execution_service import ExecutionService
from app.services.schedule_service import (
    ScheduleConfigError,
    build_schedule_payload,
    is_schedule_due,
)
from celery_config import celery_app

load_dotenv()

logger = logging.getLogger(__name__)
SCHEDULE_LOCK_TTL_SECONDS = 60 * 60 * 24

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - depends on optional redis package in runtime env
    Redis = Any  # type: ignore[assignment]


def _create_task_session_factory() -> async_sessionmaker[AsyncSession]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
    )
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def _redis_url() -> str:
    return (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()


def _compute_indegree(definition: dict[str, Any]) -> dict[str, int]:
    indegree: dict[str, int] = {
        str(node.get("id")): 0
        for node in definition.get("nodes", [])
        if node.get("id")
    }
    for edge in definition.get("edges", []):
        target = str(edge.get("target") or "")
        if target in indegree:
            indegree[target] += 1
    return indegree


async def _acquire_schedule_lock(
    redis_client: Redis,
    *,
    workflow_id: UUID,
    node_id: str,
    minute_bucket: str,
) -> bool:
    key = f"autoflow:schedule:{workflow_id}:{node_id}:{minute_bucket}"
    locked = await redis_client.set(
        key,
        "1",
        nx=True,
        ex=SCHEDULE_LOCK_TTL_SECONDS,
    )
    return bool(locked)


async def _scan_scheduled_workflows() -> dict[str, int]:
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    minute_bucket = now_utc.isoformat()

    session_factory = _create_task_session_factory()
    engine = session_factory.kw["bind"]
    redis_client: Redis | None = None

    scanned_workflows = 0
    scanned_schedule_nodes = 0
    due_schedule_nodes = 0
    enqueued = 0
    failed = 0

    try:
        try:
            if Redis is not Any:
                redis_client = Redis.from_url(_redis_url(), decode_responses=True)
        except Exception:
            redis_client = None

        async with session_factory() as db:
            execution_service = ExecutionService(db)
            workflows = (
                await db.scalars(select(Workflow).where(Workflow.is_published.is_(True)))
            ).all()
            scanned_workflows = len(workflows)

            for workflow in workflows:
                definition = workflow.definition if isinstance(workflow.definition, dict) else {}
                indegree = _compute_indegree(definition)
                nodes = definition.get("nodes", [])
                if not isinstance(nodes, list):
                    continue

                owner = await db.get(User, workflow.user_id)
                if owner is None:
                    logger.warning(
                        "Skipping schedule scan for workflow %s: owner not found.",
                        workflow.id,
                    )
                    continue

                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    if node.get("type") != "schedule_trigger":
                        continue

                    node_id = str(node.get("id") or "")
                    if not node_id:
                        continue
                    if indegree.get(node_id, 0) != 0:
                        # Schedule trigger should behave like other root triggers.
                        continue

                    scanned_schedule_nodes += 1
                    config = node.get("config") if isinstance(node.get("config"), dict) else {}

                    try:
                        is_due = is_schedule_due(config, now_utc=now_utc)
                    except ScheduleConfigError as exc:
                        logger.warning(
                            "Invalid schedule config for workflow=%s node=%s: %s",
                            workflow.id,
                            node_id,
                            exc,
                        )
                        continue

                    if not is_due:
                        continue
                    due_schedule_nodes += 1

                    try:
                        if redis_client is not None:
                            should_enqueue = await _acquire_schedule_lock(
                                redis_client,
                                workflow_id=workflow.id,
                                node_id=node_id,
                                minute_bucket=minute_bucket,
                            )
                            if not should_enqueue:
                                continue

                        schedule_payload = build_schedule_payload(
                            config=config,
                            node_id=node_id,
                            fired_at_utc=now_utc,
                        )

                        await execution_service.create_schedule_execution(
                            workflow_id=workflow.id,
                            user=owner,
                            start_node_id=node_id,
                            schedule_payload=schedule_payload,
                            require_published=True,
                        )
                        enqueued += 1
                    except Exception:
                        failed += 1
                        logger.exception(
                            "Failed to enqueue scheduled execution for workflow=%s node=%s",
                            workflow.id,
                            node_id,
                        )

    finally:
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass
        await engine.dispose()

    return {
        "scanned_workflows": scanned_workflows,
        "scanned_schedule_nodes": scanned_schedule_nodes,
        "due_schedule_nodes": due_schedule_nodes,
        "enqueued": enqueued,
        "failed": failed,
    }


@celery_app.task(name="app.tasks.scheduled_triggers.scan_scheduled_workflows")
def scan_scheduled_workflows() -> dict[str, int]:
    return asyncio.run(_scan_scheduled_workflows())

from __future__ import annotations

import asyncio
import logging
import os
from math import ceil
from datetime import datetime, timezone
from datetime import timedelta
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.error_messages import to_user_friendly_error_message
from app.execution.constants import MANUAL_STOP_ERROR_MESSAGE
from app.execution.dag_executor import DagExecutor, NodeExecutionError, WorkflowStopRequested
from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.workflows import Workflow
from celery_config import (
    WORKFLOW_EXECUTION_QUEUE,
    WORKFLOW_NODE_RESUME_QUEUE,
    celery_app,
)

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional runtime dependency
    Redis = Any  # type: ignore[assignment]

load_dotenv()
WORKFLOW_INACTIVE_ERROR_MESSAGE = "Workflow is inactive. Please activate workflow first."
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


WORKFLOW_MAX_PARALLEL_NODES = max(0, _env_int("WORKFLOW_MAX_PARALLEL_NODES", 5))
WORKFLOW_INFLIGHT_TTL_SECONDS = max(10, _env_int("WORKFLOW_INFLIGHT_TTL_SECONDS", 60 * 15))
WORKFLOW_CONCURRENCY_REQUEUE_MIN_SECONDS = max(
    1, _env_int("WORKFLOW_CONCURRENCY_REQUEUE_MIN_SECONDS", 1)
)
WORKFLOW_CONCURRENCY_REQUEUE_MAX_SECONDS = max(
    WORKFLOW_CONCURRENCY_REQUEUE_MIN_SECONDS,
    _env_int("WORKFLOW_CONCURRENCY_REQUEUE_MAX_SECONDS", 3),
)
WORKFLOW_CONCURRENCY_REQUEUE_MAX_ATTEMPTS = max(
    1,
    _env_int("WORKFLOW_CONCURRENCY_REQUEUE_MAX_ATTEMPTS", 120),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_manual_stop_error(message: str | None) -> bool:
    return str(message or "").strip().startswith(MANUAL_STOP_ERROR_MESSAGE)


def _friendly_error_message(
    error: Any,
    *,
    node_type: str | None = None,
    fallback: str = "Something went wrong while running this step.",
) -> str:
    return to_user_friendly_error_message(
        error,
        node_type=node_type,
        fallback=fallback,
    )


def _redis_url() -> str:
    return (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()


async def _create_redis_client() -> Any | None:
    if Redis is Any:
        return None
    try:
        return Redis.from_url(_redis_url(), decode_responses=True)
    except Exception:
        return None


async def _acquire_execution_inflight_slot(
    redis_client: Any,
    *,
    execution_id: str,
    max_parallel_nodes: int,
) -> bool:
    key = f"autoflow:exec:{execution_id}:inflight"
    try:
        count = int(await redis_client.incr(key))
        await redis_client.expire(key, WORKFLOW_INFLIGHT_TTL_SECONDS)
        if count > max_parallel_nodes:
            await redis_client.decr(key)
            return False
        return True
    except Exception:
        # Fail-open if Redis is unavailable so execution is not blocked.
        return True


async def _release_execution_inflight_slot(
    redis_client: Any,
    *,
    execution_id: str,
) -> None:
    key = f"autoflow:exec:{execution_id}:inflight"
    try:
        raw = await redis_client.get(key)
        if raw is None:
            return
        remaining = int(await redis_client.decr(key))
        if remaining <= 0:
            await redis_client.delete(key)
        else:
            await redis_client.expire(key, WORKFLOW_INFLIGHT_TTL_SECONDS)
    except Exception:
        return


def _compute_concurrency_requeue_seconds(retry_count: int) -> int:
    bounded_retry = max(0, int(retry_count))
    base = WORKFLOW_CONCURRENCY_REQUEUE_MIN_SECONDS * (2 ** min(2, bounded_retry))
    return max(
        WORKFLOW_CONCURRENCY_REQUEUE_MIN_SECONDS,
        min(WORKFLOW_CONCURRENCY_REQUEUE_MAX_SECONDS, base),
    )


async def _resolve_credentials(
    definition: dict[str, Any],
    db: AsyncSession,
    user_id: Any,
) -> dict[str, dict[str, Any]]:
    """
    Scans every node config in the workflow definition for a 'credential_id',
    fetches the AppCredential row, decrypts sensitive fields, and returns:
    str(credential_id) -> token_data dict (decrypted where applicable).

    This must be called in the async context so we can use the async DB session
    safely. The returned plain dict is passed into runner_context so sync runners
    can access credentials without needing their own async DB call.
    """
    from app.models.credential import AppCredential
    from app.core.security import decrypt_data

    resolved: dict[str, dict[str, Any]] = {}
    for node in definition.get("nodes", []):
        cred_id = node.get("config", {}).get("credential_id")
        if not cred_id or str(cred_id) in resolved:
            continue
        try:
            row = await db.get(AppCredential, UUID(str(cred_id)))
        except Exception:
            continue
        if row is None or str(row.user_id) != str(user_id):
            continue
        token_data = dict(row.token_data or {})
        decrypted: dict[str, Any] = {}
        for key, value in token_data.items():
            if not isinstance(value, str):
                decrypted[key] = value
                continue
            if key in {
                "api_key",
                "access_token",
                "bot_token",
                "chat_id",
                "app_password",
                "password",
                "email",
                "user_email",
                "username",
                "service_account_json",
                "serviceAccountJson",
                "private_key",
                "privateKey",
                "access_token",
                "refresh_token",
                "id_token",
                "webhook_url",
                "channel",
            }:
                try:
                    decrypted[key] = decrypt_data(value)
                except Exception:
                    # Backward compatibility for older plaintext rows
                    decrypted[key] = value
                continue
            decrypted[key] = value

        # Normalize token aliases for integrations that may use either key.
        if "api_key" not in decrypted and isinstance(decrypted.get("bot_token"), str):
            decrypted["api_key"] = decrypted["bot_token"]
        if "bot_token" not in decrypted and isinstance(decrypted.get("api_key"), str):
            decrypted["bot_token"] = decrypted["api_key"]
        if "chat_id" not in decrypted and isinstance(decrypted.get("chatId"), str):
            decrypted["chat_id"] = decrypted["chatId"]
        if "chatId" not in decrypted and isinstance(decrypted.get("chat_id"), str):
            decrypted["chatId"] = decrypted["chat_id"]
        if "app_password" not in decrypted and isinstance(decrypted.get("password"), str):
            decrypted["app_password"] = decrypted["password"]
        if "password" not in decrypted and isinstance(decrypted.get("app_password"), str):
            decrypted["password"] = decrypted["app_password"]
        if "email" not in decrypted and isinstance(decrypted.get("user_email"), str):
            decrypted["email"] = decrypted["user_email"]
        if "user_email" not in decrypted and isinstance(decrypted.get("email"), str):
            decrypted["user_email"] = decrypted["email"]
        if "username" not in decrypted and isinstance(decrypted.get("email"), str):
            decrypted["username"] = decrypted["email"]
        if "service_account_json" not in decrypted and isinstance(
            decrypted.get("serviceAccountJson"), str
        ):
            decrypted["service_account_json"] = decrypted["serviceAccountJson"]
        if "serviceAccountJson" not in decrypted and isinstance(
            decrypted.get("service_account_json"), str
        ):
            decrypted["serviceAccountJson"] = decrypted["service_account_json"]

        resolved[str(cred_id)] = decrypted
    return resolved


def _find_inline_subnode_configs(
    definition: dict[str, Any],
    target_node_id: str,
) -> list[dict[str, Any]]:
    """Returns config sub-nodes that should execute inline before the target."""
    supported_subnode_types = {"chat_model_openai", "chat_model_groq"}
    nodes_by_id = {n["id"]: n for n in definition.get("nodes", [])}
    subnode_configs: list[dict[str, Any]] = []

    for edge in definition.get("edges", []):
        if edge.get("target") != target_node_id:
            continue

        source_id = edge.get("source")
        source_node = nodes_by_id.get(source_id)
        if source_node is None or source_node.get("type") not in supported_subnode_types:
            continue

        subnode_configs.append(
            {
                "node_id": source_id,
                "node_type": source_node["type"],
                "target_handle": edge.get("targetHandle"),
                "config": source_node.get("config", {}),
            }
        )

    return subnode_configs


def _create_task_session_factory() -> async_sessionmaker[AsyncSession]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Add it to your .env file.")

    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
    )
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def _upsert_node_row(
    *,
    node_execution_by_id: dict[str, NodeExecution],
    execution: Execution,
    db,
    node_id: str,
    node_type: str,
) -> NodeExecution:
    row = node_execution_by_id.get(node_id)
    if row is None:
        row = NodeExecution(
            execution_id=execution.id,
            node_id=node_id,
            node_type=node_type,
        )
        db.add(row)
        node_execution_by_id[node_id] = row
    return row


def _build_effective_definition(
    definition: dict[str, Any] | None,
    *,
    loop_control_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _parse_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        return None

    effective = dict(definition or {})
    base_loop_control = effective.get("loop_control")
    if not isinstance(base_loop_control, dict):
        base_loop_control = {}

    merged_loop_control = {
        "enabled": bool(base_loop_control.get("enabled", False)),
        "max_node_executions": int(base_loop_control.get("max_node_executions", 3) or 3),
        "max_total_node_executions": int(
            base_loop_control.get("max_total_node_executions", 500) or 500
        ),
    }

    if isinstance(loop_control_override, dict):
        parsed_enabled = _parse_bool(loop_control_override.get("enabled"))
        if parsed_enabled is not None:
            merged_loop_control["enabled"] = parsed_enabled

        if loop_control_override.get("max_node_executions") is not None:
            try:
                merged_loop_control["max_node_executions"] = max(
                    1, int(loop_control_override["max_node_executions"])
                )
            except Exception:
                pass
        if loop_control_override.get("max_total_node_executions") is not None:
            try:
                merged_loop_control["max_total_node_executions"] = max(
                    1, int(loop_control_override["max_total_node_executions"])
                )
            except Exception:
                pass

    effective["loop_control"] = merged_loop_control
    return effective


async def _run_execution(
    *,
    execution_id: str,
    initial_payload: dict[str, Any] | None = None,
    start_node_id: str | None = None,
    start_target_handle: str | None = None,
    resume: bool = False,
    merge_source_node_id: str | None = None,
    guard_retry_count: int = 0,
    loop_control_override: dict[str, Any] | None = None,
    loop_runtime_state: dict[str, Any] | None = None,
) -> None:
    session_factory = _create_task_session_factory()
    engine = session_factory.kw["bind"]
    redis_client: Any | None = None
    inflight_slot_acquired = False

    try:
        redis_client = await _create_redis_client()
        async with session_factory() as db:
            execution = await db.scalar(
                select(Execution).where(Execution.id == UUID(execution_id))
            )
            if execution is None:
                raise ValueError(f"Execution '{execution_id}' was not found")

            workflow = await db.scalar(
                select(Workflow).where(
                    Workflow.id == execution.workflow_id,
                    Workflow.user_id == execution.user_id,
                )
            )
            if workflow is None:
                raise ValueError(
                    f"Workflow '{execution.workflow_id}' for execution '{execution_id}' was not found"
                )
            if not bool(getattr(workflow, "is_active", True)):
                execution.status = "FAILED"
                execution.finished_at = _utcnow()
                execution.error_message = WORKFLOW_INACTIVE_ERROR_MESSAGE
                await db.commit()
                return

            if execution.status == "FAILED" and _is_manual_stop_error(execution.error_message):
                return
            if execution.status == "FAILED":
                return
            if execution.status == "SUCCEEDED":
                return

            if WORKFLOW_MAX_PARALLEL_NODES > 0 and redis_client is not None:
                inflight_slot_acquired = await _acquire_execution_inflight_slot(
                    redis_client,
                    execution_id=str(execution.id),
                    max_parallel_nodes=WORKFLOW_MAX_PARALLEL_NODES,
                )
                if not inflight_slot_acquired:
                    if guard_retry_count >= WORKFLOW_CONCURRENCY_REQUEUE_MAX_ATTEMPTS:
                        execution.status = "FAILED"
                        execution.finished_at = _utcnow()
                        execution.error_message = (
                            "Concurrency guard retry limit reached while waiting for an "
                            "execution slot. Increase WORKFLOW_MAX_PARALLEL_NODES or reduce fan-out."
                        )
                        await db.commit()
                        return

                    if start_node_id:
                        start_node = next(
                            (
                                node
                                for node in workflow.definition.get("nodes", [])
                                if node.get("id") == start_node_id
                            ),
                            None,
                        )
                        start_row = await db.scalar(
                            select(NodeExecution).where(
                                NodeExecution.execution_id == execution.id,
                                NodeExecution.node_id == start_node_id,
                            )
                        )
                        if start_row is None:
                            start_row = NodeExecution(
                                execution_id=execution.id,
                                node_id=start_node_id,
                                node_type=str(
                                    start_node.get("type")
                                    if isinstance(start_node, dict)
                                    else "unknown"
                                ),
                            )
                            db.add(start_row)
                        start_row.status = "QUEUED"
                        if initial_payload is not None and start_row.input_data is None:
                            start_row.input_data = initial_payload
                        start_row.error_message = None
                    execution.status = "WAITING"
                    execution.finished_at = None
                    execution.error_message = None
                    await db.commit()

                    run_execution.apply_async(
                        kwargs={
                            "execution_id": str(execution.id),
                            "initial_payload": initial_payload,
                            "start_node_id": start_node_id,
                            "start_target_handle": start_target_handle,
                            "resume": resume,
                            "merge_source_node_id": merge_source_node_id,
                            "guard_retry_count": int(guard_retry_count) + 1,
                            "loop_control_override": loop_control_override,
                            "loop_runtime_state": loop_runtime_state,
                        },
                        queue=(WORKFLOW_NODE_RESUME_QUEUE if resume else WORKFLOW_EXECUTION_QUEUE),
                        countdown=_compute_concurrency_requeue_seconds(guard_retry_count),
                        retry=True,
                        retry_policy={
                            "max_retries": 8,
                            "interval_start": 0,
                            "interval_step": 1,
                            "interval_max": 8,
                        },
                    )
                    return

            is_resume_run = resume or execution.status in {"WAITING", "QUEUED"}
            execution.status = "RUNNING"
            execution.started_at = execution.started_at or _utcnow()
            execution.finished_at = None
            execution.error_message = None

            node_execution_rows = (
                await db.scalars(
                    select(NodeExecution).where(NodeExecution.execution_id == execution.id)
                )
            ).all()
            node_execution_by_id = {row.node_id: row for row in node_execution_rows}
            nodes_by_id = {
                node.get("id"): node
                for node in workflow.definition.get("nodes", [])
                if node.get("id")
            }
            if not is_resume_run:
                for row in node_execution_rows:
                    row.status = "PENDING"
                    row.input_data = None
                    row.output_data = None
                    row.error_message = None
                    row.started_at = None
                    row.finished_at = None
            elif start_node_id:
                start_node = next(
                    (
                        node
                        for node in workflow.definition.get("nodes", [])
                        if node.get("id") == start_node_id
                    ),
                    None,
                )
                start_row = _upsert_node_row(
                    node_execution_by_id=node_execution_by_id,
                    execution=execution,
                    db=db,
                    node_id=start_node_id,
                    node_type=str(start_node.get("type") if isinstance(start_node, dict) else "unknown"),
                )
                start_row.status = "QUEUED"
                if initial_payload is not None:
                    start_row.input_data = initial_payload
                start_row.error_message = None

                # Merge resume hardening:
                # delayed branches can arrive in separate worker tasks, so we persist
                # arrival state on the merge row until all required inputs are accounted.
                if isinstance(start_node, dict) and str(start_node.get("type")) == "merge":
                    subnode_types = {"chat_model_openai", "chat_model_groq"}
                    incoming_parent_ids = [
                        str(edge.get("source"))
                        for edge in workflow.definition.get("edges", [])
                        if str(edge.get("target")) == start_node_id
                        and str(edge.get("source")) in nodes_by_id
                        and str(
                            (nodes_by_id.get(str(edge.get("source"))) or {}).get("type") or ""
                        )
                        not in subnode_types
                    ]
                    expected_inputs = len(incoming_parent_ids)

                    runtime_state: dict[str, Any] = {}
                    if isinstance(start_row.output_data, dict):
                        runtime_state = dict(
                            start_row.output_data.get("__runtime_merge_state") or {}
                        )
                    raw_input_by_source = runtime_state.get("input_by_source")
                    input_by_source = (
                        dict(raw_input_by_source)
                        if isinstance(raw_input_by_source, dict)
                        else {}
                    )
                    if not input_by_source:
                        raw_payload_by_source = runtime_state.get("payload_by_source")
                        if isinstance(raw_payload_by_source, dict):
                            for key, payload in raw_payload_by_source.items():
                                input_by_source[str(key)] = {
                                    "handle": None,
                                    "data": payload,
                                }

                    source_key = str(
                        merge_source_node_id
                        or f"__arrival_{len(input_by_source) + 1}"
                    )
                    input_by_source[source_key] = {
                        "handle": start_target_handle,
                        "data": (
                            initial_payload
                            if isinstance(initial_payload, dict)
                            else {"_default": initial_payload}
                        ),
                    }

                    parent_rows = []
                    if incoming_parent_ids:
                        parent_rows = (
                            await db.scalars(
                                select(NodeExecution).where(
                                    NodeExecution.execution_id == execution.id,
                                    NodeExecution.node_id.in_(incoming_parent_ids),
                                )
                            )
                        ).all()
                    status_by_parent = {
                        row.node_id: str(row.status or "").upper()
                        for row in parent_rows
                    }

                    received_parents = [
                        parent_id
                        for parent_id in incoming_parent_ids
                        if parent_id in input_by_source
                    ]
                    blocked_parents = [
                        parent_id
                        for parent_id in incoming_parent_ids
                        if parent_id not in input_by_source
                        and status_by_parent.get(parent_id) in {"SKIPPED", "BLOCKED"}
                    ]

                    received_inputs = len(received_parents)
                    blocked_inputs = len(blocked_parents)
                    accounted_inputs = received_inputs + blocked_inputs

                    runtime_state.update(
                        {
                            "input_by_source": input_by_source,
                            "received_inputs": received_inputs,
                            "blocked_inputs": blocked_inputs,
                            "expected_inputs": expected_inputs,
                            "last_update_at": _utcnow().isoformat(),
                        }
                    )

                    start_row.status = "QUEUED"
                    start_row.input_data = {
                        "received_inputs": received_inputs,
                        "blocked_inputs": blocked_inputs,
                        "expected_inputs": expected_inputs,
                    }
                    start_row.output_data = {"__runtime_merge_state": runtime_state}
                    start_row.error_message = None

                    if expected_inputs > 0 and accounted_inputs < expected_inputs:
                        execution.status = "WAITING"
                        execution.finished_at = None
                        execution.error_message = None
                        await db.commit()
                        return

                    if expected_inputs > 0 and received_inputs == 0 and accounted_inputs >= expected_inputs:
                        start_row.status = "SKIPPED"
                        start_row.error_message = "All incoming merge branches were blocked."
                        start_row.finished_at = _utcnow()
                        execution.status = "WAITING"
                        execution.finished_at = None
                        execution.error_message = None
                        await db.commit()
                        return

                    if expected_inputs > 0:
                        initial_payload = {
                            "__merge_inputs__": [
                                input_by_source[parent_id]
                                for parent_id in incoming_parent_ids
                                if parent_id in input_by_source
                            ],
                            "__merge_blocked_inputs__": blocked_inputs,
                        }
                        # Clear runtime buffer once merge is ready to run.
                        start_row.output_data = None

            await db.commit()

            try:
                resolved_credential_data = await _resolve_credentials(
                    definition=workflow.definition,
                    db=db,
                    user_id=execution.user_id,
                )
                resolved_credentials = {
                    credential_id: (
                        str(token_data.get("api_key") or token_data.get("bot_token") or token_data.get("access_token") or "")
                    )
                    for credential_id, token_data in resolved_credential_data.items()
                    if token_data.get("api_key") or token_data.get("bot_token") or token_data.get("access_token")
                }

                progress_lock = asyncio.Lock()
                loop = asyncio.get_running_loop()
                deferred_branch_count = 0

                effective_definition = _build_effective_definition(
                    workflow.definition,
                    loop_control_override=loop_control_override,
                )

                async def _persist_node_progress(
                    *,
                    node_id: str,
                    node_type: str,
                    status: str,
                    input_data: Any = None,
                    output_data: Any = None,
                    error_message: str | None = None,
                ) -> None:
                    async with progress_lock:
                        await db.refresh(execution)
                        if execution.status not in {"RUNNING", "WAITING"}:
                            raise WorkflowStopRequested(
                                execution.error_message or MANUAL_STOP_ERROR_MESSAGE
                            )

                        row = _upsert_node_row(
                            node_execution_by_id=node_execution_by_id,
                            execution=execution,
                            db=db,
                            node_id=node_id,
                            node_type=node_type,
                        )
                        now = _utcnow()
                        normalized_error_message: str | None = None
                        if error_message:
                            if status in {"FAILED", "BLOCKED", "SKIPPED"}:
                                normalized_error_message = _friendly_error_message(
                                    error_message,
                                    node_type=node_type,
                                )
                            else:
                                normalized_error_message = str(error_message)

                        if status == "RUNNING":
                            row.status = "RUNNING"
                            row.input_data = input_data
                            row.error_message = None
                            row.started_at = row.started_at or now
                            row.finished_at = None
                        elif status == "SUCCEEDED":
                            row.status = "SUCCEEDED"
                            if input_data is not None and row.input_data is None:
                                row.input_data = input_data
                            row.output_data = output_data
                            row.error_message = None
                            row.started_at = row.started_at or now
                            row.finished_at = now
                        elif status == "FAILED":
                            row.status = "FAILED"
                            if input_data is not None:
                                row.input_data = input_data
                            row.output_data = None
                            row.error_message = normalized_error_message
                            row.started_at = row.started_at or now
                            row.finished_at = now
                        elif status in {"QUEUED", "WAITING", "SKIPPED", "BLOCKED"}:
                            row.status = status
                            if input_data is not None:
                                row.input_data = input_data
                            if output_data is not None:
                                row.output_data = output_data
                            row.error_message = normalized_error_message
                            if status == "WAITING":
                                row.started_at = row.started_at or now
                                row.finished_at = None
                            elif status in {"SKIPPED", "BLOCKED"}:
                                row.started_at = row.started_at or now
                                row.finished_at = row.finished_at or now
                        else:
                            row.status = status

                        await db.commit()

                def _on_node_progress(
                    *,
                    node_id: str,
                    node_type: str,
                    status: str,
                    input_data: Any = None,
                    output_data: Any = None,
                    error_message: str | None = None,
                ) -> None:
                    target_type = (
                        node_type
                        or (nodes_by_id.get(node_id, {}) or {}).get("type")
                        or "unknown"
                    )
                    future = asyncio.run_coroutine_threadsafe(
                        _persist_node_progress(
                            node_id=node_id,
                            node_type=target_type,
                            status=status,
                            input_data=input_data,
                            output_data=output_data,
                            error_message=error_message,
                        ),
                        loop,
                    )
                    future.result()

                async def _schedule_deferred_branch(
                    *,
                    source_node_id: str,
                    source_node_type: str,
                    target_node_id: str,
                    target_handle: str | None,
                    payload: Any,
                    delay_seconds: float,
                    delay_run_at: Any = None,
                    loop_runtime_state: dict[str, Any] | None = None,
                ) -> None:
                    nonlocal deferred_branch_count
                    async with progress_lock:
                        await db.refresh(execution)
                        if execution.status == "FAILED" and _is_manual_stop_error(execution.error_message):
                            raise WorkflowStopRequested(
                                execution.error_message or MANUAL_STOP_ERROR_MESSAGE
                            )

                        safe_delay_seconds = 0.0
                        try:
                            safe_delay_seconds = max(0.0, float(delay_seconds or 0.0))
                        except Exception:
                            safe_delay_seconds = 0.0

                        eta: datetime | None = None
                        if isinstance(delay_run_at, (int, float)):
                            eta = datetime.fromtimestamp(float(delay_run_at), tz=timezone.utc)
                        elif isinstance(delay_run_at, str) and delay_run_at.strip():
                            candidate = delay_run_at.strip()
                            if candidate.endswith("Z"):
                                candidate = f"{candidate[:-1]}+00:00"
                            try:
                                parsed = datetime.fromisoformat(candidate)
                                if parsed.tzinfo is None:
                                    parsed = parsed.replace(tzinfo=timezone.utc)
                                eta = parsed.astimezone(timezone.utc)
                            except Exception:
                                eta = None

                        if eta is None and safe_delay_seconds > 0:
                            eta = _utcnow() + timedelta(seconds=safe_delay_seconds)
                        if eta is None:
                            eta = _utcnow()
                        if eta < _utcnow() and safe_delay_seconds > 0:
                            eta = _utcnow() + timedelta(seconds=safe_delay_seconds)
                        elif eta < _utcnow():
                            eta = _utcnow()

                        target_node = nodes_by_id.get(target_node_id, {})
                        deferred_is_time_wait = safe_delay_seconds > 0
                        target_row = _upsert_node_row(
                            node_execution_by_id=node_execution_by_id,
                            execution=execution,
                            db=db,
                            node_id=target_node_id,
                            node_type=str(target_node.get("type") or "unknown"),
                        )
                        target_row.status = "WAITING" if deferred_is_time_wait else "QUEUED"
                        target_row.input_data = payload if isinstance(payload, dict) else {"_default": payload}
                        target_row.output_data = None
                        target_row.error_message = None
                        now_for_row = _utcnow()
                        target_row.started_at = target_row.started_at or now_for_row
                        target_row.finished_at = None
                        await db.commit()

                        apply_async_kwargs: dict[str, Any] = {
                            "kwargs": {
                                "execution_id": str(execution.id),
                                "initial_payload": payload if isinstance(payload, dict) else {"_default": payload},
                                "start_node_id": target_node_id,
                                "start_target_handle": target_handle,
                                "resume": True,
                                "merge_source_node_id": source_node_id,
                                "guard_retry_count": 0,
                                "loop_control_override": loop_control_override,
                                "loop_runtime_state": loop_runtime_state,
                            },
                            "queue": WORKFLOW_NODE_RESUME_QUEUE,
                            "retry": True,
                            "retry_policy": {
                                "max_retries": 8,
                                "interval_start": 0,
                                "interval_step": 1,
                                "interval_max": 8,
                            },
                        }
                        now = _utcnow()
                        if eta > now:
                            apply_async_kwargs["eta"] = eta
                        elif safe_delay_seconds > 0:
                            apply_async_kwargs["countdown"] = max(1, int(ceil(safe_delay_seconds)))
                        run_execution.apply_async(**apply_async_kwargs)
                        deferred_branch_count += 1

                def _on_deferred_branch(
                    *,
                    source_node_id: str,
                    source_node_type: str,
                    target_node_id: str,
                    target_handle: str | None,
                    payload: Any,
                    delay_seconds: float,
                    delay_run_at: Any = None,
                    loop_runtime_state: dict[str, Any] | None = None,
                ) -> None:
                    future = asyncio.run_coroutine_threadsafe(
                        _schedule_deferred_branch(
                            source_node_id=source_node_id,
                            source_node_type=source_node_type,
                            target_node_id=target_node_id,
                            target_handle=target_handle,
                            payload=payload,
                            delay_seconds=delay_seconds,
                            delay_run_at=delay_run_at,
                            loop_runtime_state=loop_runtime_state,
                        ),
                        loop,
                    )
                    future.result()

                result = await asyncio.to_thread(
                    DagExecutor().execute,
                    definition=effective_definition,
                    initial_payload=initial_payload,
                    start_node_id=start_node_id,
                    start_target_handle=start_target_handle,
                    runner_context={
                        "user_id": execution.user_id,
                        "resolved_credentials": resolved_credentials,
                        "resolved_credential_data": resolved_credential_data,
                        "parallel_fanout_enabled": True,
                        "loop_runtime_state": loop_runtime_state if isinstance(loop_runtime_state, dict) else None,
                    },
                    progress_callback=_on_node_progress,
                    defer_callback=_on_deferred_branch,
                )

                await db.refresh(execution)
                if execution.status != "RUNNING":
                    return

                visited_nodes = result.get("visited_nodes", [])
                node_inputs = result.get("node_inputs", {})
                node_outputs = result.get("node_outputs", {})

                # Persist succeeded nodes in the actual execution order.
                # This allows frontends to sort logs by the order nodes were visited.
                for node_id in visited_nodes:
                    node_def = nodes_by_id.get(node_id)
                    row = _upsert_node_row(
                        node_execution_by_id=node_execution_by_id,
                        execution=execution,
                        db=db,
                        node_id=node_id,
                        node_type=node_def["type"] if node_def is not None else "unknown",
                    )
                    row.status = "SUCCEEDED"
                    row.input_data = node_inputs.get(node_id) if row.input_data is None else row.input_data
                    row.output_data = node_outputs.get(node_id)
                    row.error_message = None
                    row.started_at = row.started_at or execution.started_at
                    row.finished_at = row.finished_at or _utcnow()

                active_statuses = {"RUNNING", "QUEUED", "WAITING"}
                has_active_nodes = any(
                    (row.status or "").upper() in active_statuses
                    for row in node_execution_by_id.values()
                )
                if deferred_branch_count > 0 or has_active_nodes:
                    execution.status = "WAITING"
                    execution.finished_at = None
                else:
                    execution.status = "SUCCEEDED"
                    execution.finished_at = _utcnow()
                execution.error_message = None
                await db.commit()
            except NodeExecutionError as exc:
                await db.refresh(execution)
                if execution.status != "RUNNING":
                    return

                now = _utcnow()
                visited_node_ids = set(exc.visited_nodes or [])
                user_error_message = exc.user_message or _friendly_error_message(
                    exc,
                    node_type=exc.node_type,
                )
                logger.exception(
                    "Workflow execution failed at node '%s' (%s): %s",
                    exc.node_id,
                    exc.node_type,
                    exc.debug_message,
                )

                # Persist the successfully completed path first.
                for node_id in exc.visited_nodes or []:
                    node_def = nodes_by_id.get(node_id)
                    if node_def is None:
                        continue
                    row = _upsert_node_row(
                        node_execution_by_id=node_execution_by_id,
                        execution=execution,
                        db=db,
                        node_id=node_id,
                        node_type=node_def["type"],
                    )
                    row.status = "SUCCEEDED"
                    if row.input_data is None:
                        row.input_data = (exc.node_inputs or {}).get(node_id)
                    row.output_data = (exc.node_outputs or {}).get(node_id)
                    row.error_message = None
                    row.started_at = row.started_at or execution.started_at
                    row.finished_at = row.finished_at or now

                for node in workflow.definition.get("nodes", []):
                    node_id = node["id"]
                    row = _upsert_node_row(
                        node_execution_by_id=node_execution_by_id,
                        execution=execution,
                        db=db,
                        node_id=node_id,
                        node_type=node["type"],
                    )

                    if node_id == exc.node_id:
                        row.status = "FAILED"
                        row.input_data = exc.input_data
                        row.output_data = None
                        row.error_message = user_error_message
                        row.started_at = row.started_at or execution.started_at
                        row.finished_at = row.finished_at or now
                    elif node_id not in visited_node_ids:
                        row.status = "PENDING"
                        row.input_data = None
                        row.output_data = None
                        row.error_message = None
                        row.started_at = None
                        row.finished_at = None

                execution.status = "FAILED"
                execution.finished_at = now
                execution.error_message = user_error_message
                await db.commit()
                return
            except WorkflowStopRequested:
                await db.refresh(execution)
                if execution.status == "FAILED" and _is_manual_stop_error(execution.error_message):
                    return

                execution.status = "FAILED"
                execution.finished_at = _utcnow()
                execution.error_message = MANUAL_STOP_ERROR_MESSAGE
                await db.commit()
                return
            except Exception as exc:
                await db.refresh(execution)
                if execution.status == "FAILED" and _is_manual_stop_error(execution.error_message):
                    return

                user_error_message = _friendly_error_message(
                    exc,
                    fallback="Workflow execution failed unexpectedly.",
                )
                logger.exception(
                    "Workflow execution crashed for execution '%s': %s",
                    execution_id,
                    str(exc),
                )
                execution.status = "FAILED"
                execution.finished_at = _utcnow()
                execution.error_message = user_error_message
                await db.commit()
                raise
    finally:
        if inflight_slot_acquired and redis_client is not None:
            await _release_execution_inflight_slot(
                redis_client,
                execution_id=execution_id,
            )
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass
        await engine.dispose()


async def _run_node_test(
    *,
    execution_id: str,
    node_id: str,
    input_data: dict[str, Any] | None = None,
) -> None:
    session_factory = _create_task_session_factory()
    engine = session_factory.kw["bind"]

    try:
        async with session_factory() as db:
            execution = await db.scalar(
                select(Execution).where(Execution.id == UUID(execution_id))
            )
            if execution is None:
                raise ValueError(f"Execution '{execution_id}' was not found")

            workflow = await db.scalar(
                select(Workflow).where(
                    Workflow.id == execution.workflow_id,
                    Workflow.user_id == execution.user_id,
                )
            )
            if workflow is None:
                raise ValueError(f"Workflow '{execution.workflow_id}' not found")

            # Find the node config
            node_def = next((n for n in workflow.definition.get("nodes", []) if n["id"] == node_id), None)
            if not node_def:
                raise ValueError(f"Node '{node_id}' not found in definition")

            execution.status = "RUNNING"
            execution.started_at = _utcnow()

            node_row = await db.scalar(
                select(NodeExecution).where(
                    NodeExecution.execution_id == execution.id,
                    NodeExecution.node_id == node_id
                )
            )
            if node_row is None:
                node_row = NodeExecution(
                    execution_id=execution.id,
                    node_id=node_id,
                    node_type=node_def["type"],
                )
                db.add(node_row)

            node_row.status = "RUNNING"
            node_row.started_at = execution.started_at
            node_row.input_data = input_data
            await db.commit()

            # Pre-resolve credentials from the whole workflow definition
            # (so chat_model nodes' credentials are also available)
            resolved_credential_data = await _resolve_credentials(
                definition=workflow.definition,
                db=db,
                user_id=execution.user_id,
            )
            resolved_credentials = {
                credential_id: (
                    str(token_data.get("api_key") or token_data.get("bot_token") or token_data.get("access_token") or "")
                )
                for credential_id, token_data in resolved_credential_data.items()
                if token_data.get("api_key") or token_data.get("bot_token") or token_data.get("access_token")
            }

            subnode_configs = _find_inline_subnode_configs(
                definition=workflow.definition,
                target_node_id=node_id,
            )

            # Execute single node
            res = DagExecutor().execute_node(
                node_id=node_id,
                node_type=node_def["type"],
                config=node_def.get("config", {}),
                input_data=input_data,
                runner_context={
                    "user_id": execution.user_id,
                    "resolved_credentials": resolved_credentials,
                    "resolved_credential_data": resolved_credential_data,
                },
                subnode_configs=subnode_configs,
            )


            # Update results
            node_error_message = (
                _friendly_error_message(
                    res["error_message"],
                    node_type=node_def["type"],
                )
                if res.get("error_message")
                else None
            )
            node_row.status = res["status"]
            node_row.output_data = res["output_data"]
            node_row.error_message = node_error_message
            node_row.finished_at = _utcnow()

            execution.status = res["status"]
            execution.finished_at = node_row.finished_at
            execution.error_message = node_error_message

            await db.commit()
    except Exception as exc:
        logger.exception(
            "Node test execution crashed for execution '%s', node '%s': %s",
            execution_id,
            node_id,
            str(exc),
        )
        user_error_message = _friendly_error_message(
            exc,
            fallback="Node test failed unexpectedly.",
        )
        try:
            async with session_factory() as db:
                execution = await db.scalar(
                    select(Execution).where(Execution.id == UUID(execution_id))
                )
                if execution is not None:
                    execution.status = "FAILED"
                    execution.finished_at = _utcnow()
                    execution.error_message = user_error_message

                    node_row = await db.scalar(
                        select(NodeExecution).where(
                            NodeExecution.execution_id == execution.id,
                            NodeExecution.node_id == node_id,
                        )
                    )
                    if node_row is None:
                        node_row = NodeExecution(
                            execution_id=execution.id,
                            node_id=node_id,
                            node_type="unknown",
                        )
                        db.add(node_row)
                    node_row.status = "FAILED"
                    node_row.error_message = user_error_message
                    node_row.finished_at = _utcnow()
                    await db.commit()
        except Exception:
            logger.exception(
                "Failed to persist node test failure for execution '%s'",
                execution_id,
            )
        raise
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.execute_workflow.run_execution")
def run_execution(
    execution_id: str,
    initial_payload: dict[str, Any] | None = None,
    start_node_id: str | None = None,
    start_target_handle: str | None = None,
    resume: bool = False,
    merge_source_node_id: str | None = None,
    guard_retry_count: int = 0,
    loop_control_override: dict[str, Any] | None = None,
    loop_runtime_state: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    # Forward-compatible shim: ignore unexpected kwargs from mixed-version senders.
    if loop_control_override is None and isinstance(kwargs.get("loop_control_override"), dict):
        loop_control_override = kwargs.get("loop_control_override")
    if loop_runtime_state is None and isinstance(kwargs.get("loop_runtime_state"), dict):
        loop_runtime_state = kwargs.get("loop_runtime_state")
    if start_target_handle is None and kwargs.get("start_target_handle") is not None:
        start_target_handle = str(kwargs.get("start_target_handle"))
    if not resume and kwargs.get("resume") is not None:
        raw_resume = kwargs.get("resume")
        if isinstance(raw_resume, bool):
            resume = raw_resume
        elif isinstance(raw_resume, (int, float)):
            resume = bool(raw_resume)
        elif isinstance(raw_resume, str):
            resume = raw_resume.strip().lower() in {"1", "true", "yes", "on"}
    if kwargs.get("guard_retry_count") is not None:
        try:
            guard_retry_count = max(0, int(kwargs.get("guard_retry_count")))
        except Exception:
            guard_retry_count = 0
    if merge_source_node_id is None and kwargs.get("merge_source_node_id") is not None:
        merge_source_node_id = str(kwargs.get("merge_source_node_id"))
    asyncio.run(
        _run_execution(
            execution_id=execution_id,
            initial_payload=initial_payload,
            start_node_id=start_node_id,
            start_target_handle=start_target_handle,
            resume=resume,
            merge_source_node_id=merge_source_node_id,
            guard_retry_count=guard_retry_count,
            loop_control_override=loop_control_override,
            loop_runtime_state=loop_runtime_state,
        )
    )


@celery_app.task(name="app.tasks.execute_workflow.run_node_test")
def run_node_test(
    execution_id: str,
    node_id: str,
    input_data: dict[str, Any] | None = None,
) -> None:
    asyncio.run(
        _run_node_test(
            execution_id=execution_id,
            node_id=node_id,
            input_data=input_data,
        )
    )

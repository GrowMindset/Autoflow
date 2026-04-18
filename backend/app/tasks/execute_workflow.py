from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.execution.constants import MANUAL_STOP_ERROR_MESSAGE
from app.execution.dag_executor import DagExecutor, NodeExecutionError, WorkflowStopRequested
from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.workflows import Workflow
from celery_config import celery_app

load_dotenv()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_manual_stop_error(message: str | None) -> bool:
    return str(message or "").strip().startswith(MANUAL_STOP_ERROR_MESSAGE)


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
    loop_control_override: dict[str, Any] | None = None,
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
                raise ValueError(
                    f"Workflow '{execution.workflow_id}' for execution '{execution_id}' was not found"
                )

            if execution.status == "FAILED" and _is_manual_stop_error(execution.error_message):
                return
            if execution.status == "SUCCEEDED":
                return

            execution.status = "RUNNING"
            execution.started_at = _utcnow()
            execution.finished_at = None
            execution.error_message = None

            node_execution_rows = (
                await db.scalars(
                    select(NodeExecution).where(NodeExecution.execution_id == execution.id)
                )
            ).all()
            node_execution_by_id = {row.node_id: row for row in node_execution_rows}
            for row in node_execution_rows:
                row.status = "PENDING"
                row.input_data = None
                row.output_data = None
                row.error_message = None
                row.started_at = None
                row.finished_at = None

            await db.commit()

            try:
                nodes_by_id = {
                    node.get("id"): node
                    for node in workflow.definition.get("nodes", [])
                    if node.get("id")
                }
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
                        if execution.status != "RUNNING":
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
                            row.error_message = error_message
                            row.started_at = row.started_at or now
                            row.finished_at = now
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

                result = await asyncio.to_thread(
                    DagExecutor().execute,
                    definition=effective_definition,
                    initial_payload=initial_payload,
                    start_node_id=start_node_id,
                    runner_context={
                        "user_id": execution.user_id,
                        "resolved_credentials": resolved_credentials,
                        "resolved_credential_data": resolved_credential_data,
                    },
                    progress_callback=_on_node_progress,
                )

                await db.refresh(execution)
                if execution.status != "RUNNING":
                    return

                visited_nodes = result.get("visited_nodes", [])
                node_inputs = result.get("node_inputs", {})
                node_outputs = result.get("node_outputs", {})

                visited_node_ids = set(visited_nodes)

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

                # Mark non-visited nodes as pending
                for node in workflow.definition.get("nodes", []):
                    if node["id"] in visited_node_ids:
                        continue

                    row = _upsert_node_row(
                        node_execution_by_id=node_execution_by_id,
                        execution=execution,
                        db=db,
                        node_id=node["id"],
                        node_type=node["type"],
                    )
                    row.status = "PENDING"
                    row.input_data = None
                    row.output_data = None
                    row.error_message = None
                    row.started_at = None
                    row.finished_at = None

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
                        row.error_message = str(exc)
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
                execution.error_message = None
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

                execution.status = "FAILED"
                execution.finished_at = _utcnow()
                execution.error_message = str(exc)
                await db.commit()
                raise
    finally:
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
            node_row.status = res["status"]
            node_row.output_data = res["output_data"]
            node_row.error_message = res["error_message"]
            node_row.finished_at = _utcnow()

            execution.status = res["status"]
            execution.finished_at = node_row.finished_at
            execution.error_message = res["error_message"]

            await db.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.execute_workflow.run_execution")
def run_execution(
    execution_id: str,
    initial_payload: dict[str, Any] | None = None,
    start_node_id: str | None = None,
    loop_control_override: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    # Forward-compatible shim: ignore unexpected kwargs from mixed-version senders.
    if loop_control_override is None and isinstance(kwargs.get("loop_control_override"), dict):
        loop_control_override = kwargs.get("loop_control_override")
    asyncio.run(
        _run_execution(
            execution_id=execution_id,
            initial_payload=initial_payload,
            start_node_id=start_node_id,
            loop_control_override=loop_control_override,
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

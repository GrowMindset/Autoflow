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

from app.execution.dag_executor import DagExecutor, NodeExecutionError
from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.workflows import Workflow
from celery_config import celery_app

load_dotenv()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_credentials(
    definition: dict[str, Any],
    db: AsyncSession,
    user_id: Any,
) -> dict[str, str]:
    """
    Scans every node config in the workflow definition for a 'credential_id',
    fetches the AppCredential row, decrypts the API key, and returns a mapping
    of  str(credential_id) -> decrypted_api_key.

    This must be called in the async context so we can use the async DB session
    safely. The returned plain dict is passed into runner_context so sync runners
    can access credentials without needing their own async DB call.
    """
    from app.models.credential import AppCredential
    from app.core.security import decrypt_data

    resolved: dict[str, str] = {}
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
        encrypted = row.token_data.get("api_key")
        if encrypted:
            try:
                resolved[str(cred_id)] = decrypt_data(encrypted)
            except Exception:
                pass
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


async def _run_execution(
    *,
    execution_id: str,
    initial_payload: dict[str, Any] | None = None,
    start_node_id: str | None = None,
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
                resolved_credentials = await _resolve_credentials(
                    definition=workflow.definition,
                    db=db,
                    user_id=execution.user_id,
                )

                result = DagExecutor().execute(
                    definition=workflow.definition,
                    initial_payload=initial_payload,
                    start_node_id=start_node_id,
                    runner_context={
                        "user_id": execution.user_id,
                        "resolved_credentials": resolved_credentials,
                    }
                )

                visited_nodes = result.get("visited_nodes", [])
                node_inputs = result.get("node_inputs", {})
                node_outputs = result.get("node_outputs", {})

                visited_node_ids = set(visited_nodes)

                # Persist succeeded nodes in the actual execution order.
                # This allows frontends to sort logs by the order nodes were visited.
                for node_id in visited_nodes:
                    node_def = next((n for n in workflow.definition.get("nodes", []) if n["id"] == node_id), None)
                    row = _upsert_node_row(
                        node_execution_by_id=node_execution_by_id,
                        execution=execution,
                        db=db,
                        node_id=node_id,
                        node_type=node_def["type"] if node_def is not None else "unknown",
                    )
                    row.status = "SUCCEEDED"
                    row.input_data = node_inputs.get(node_id)
                    row.output_data = node_outputs.get(node_id)
                    row.error_message = None
                    row.started_at = execution.started_at
                    row.finished_at = _utcnow()

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
                now = _utcnow()

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
                        row.started_at = execution.started_at
                        row.finished_at = now

                execution.status = "FAILED"
                execution.finished_at = now
                execution.error_message = None
                await db.commit()
                return
            except Exception as exc:
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
            resolved_credentials = await _resolve_credentials(
                definition=workflow.definition,
                db=db,
                user_id=execution.user_id,
            )

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
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor() as executor:
        future = executor.submit(
            asyncio.run,
            _run_execution(
                execution_id=execution_id,
                initial_payload=initial_payload,
                start_node_id=start_node_id,
            )
        )
        future.result()


@celery_app.task(name="app.tasks.execute_workflow.run_node_test")
def run_node_test(
    execution_id: str,
    node_id: str,
    input_data: dict[str, Any] | None = None,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor() as executor:
        future = executor.submit(
            asyncio.run,
            _run_node_test(
                execution_id=execution_id,
                node_id=node_id,
                input_data=input_data,
            )
        )
        future.result()

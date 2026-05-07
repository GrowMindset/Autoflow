from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.security import decrypt_data
from app.execution.dag_executor import DagExecutor, NodeExecutionError
from app.models.credential import AppCredential
from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.workflows import Workflow


class ExecuteWorkflowRunner:
    """Runs a child workflow inline from a parent workflow node."""

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> Any:
        runner_context = dict(context or {})
        parent_execution_id = runner_context.get("execution_id")
        user_id = runner_context.get("user_id")
        parent_workflow_id = runner_context.get("workflow_id")
        database_url = str(
            runner_context.get("database_url")
            or os.getenv("DATABASE_URL")
            or ""
        ).strip()

        if not parent_execution_id:
            raise ValueError("ExecuteWorkflowRunner: parent execution_id is missing")
        if not user_id:
            raise ValueError("ExecuteWorkflowRunner: user_id is missing")
        if not database_url:
            raise ValueError("ExecuteWorkflowRunner: DATABASE_URL is not set")

        payload = self._build_payload(config=config, input_data=input_data)
        if str(config.get("mode") or "run_once") == "run_per_item":
            items = self._resolve_run_items(payload=payload, input_data=input_data)
            return [
                self._run_child(
                    config=config,
                    payload=item if isinstance(item, dict) else {"item": item},
                    database_url=database_url,
                    user_id=user_id,
                    parent_execution_id=parent_execution_id,
                    parent_workflow_id=parent_workflow_id,
                    parent_runner_context=runner_context,
                )
                for item in items
            ]

        return self._run_child(
            config=config,
            payload=payload,
            database_url=database_url,
            user_id=user_id,
            parent_execution_id=parent_execution_id,
            parent_workflow_id=parent_workflow_id,
            parent_runner_context=runner_context,
        )

    @staticmethod
    def _build_payload(*, config: dict[str, Any], input_data: Any) -> dict[str, Any]:
        raw_inputs = config.get("workflow_inputs")
        payload: dict[str, Any] = {}
        if isinstance(raw_inputs, list):
            for item in raw_inputs:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "").strip()
                if not key:
                    continue
                payload[key] = item.get("value")

        if payload:
            return payload
        return dict(input_data) if isinstance(input_data, dict) else {}

    @staticmethod
    def _resolve_run_items(*, payload: dict[str, Any], input_data: Any) -> list[Any]:
        for value in payload.values():
            if isinstance(value, list):
                return value
        if isinstance(input_data, dict):
            for value in input_data.values():
                if isinstance(value, list):
                    return value
        if isinstance(input_data, list):
            return list(input_data)
        raise ValueError(
            "ExecuteWorkflowRunner: run_per_item requires an array field in the input data"
        )

    def _run_child(
        self,
        *,
        config: dict[str, Any],
        payload: dict[str, Any],
        database_url: str,
        user_id: Any,
        parent_execution_id: Any,
        parent_workflow_id: Any,
        parent_runner_context: dict[str, Any],
    ) -> Any:
        engine = create_engine(self._to_sync_database_url(database_url))
        try:
            with Session(engine) as session:
                workflow, definition = self._resolve_child_workflow(
                    session=session,
                    config=config,
                    user_id=user_id,
                    parent_workflow_id=parent_workflow_id,
                )
                self._guard_circular_reference(
                    definition=definition,
                    parent_workflow_id=parent_workflow_id,
                )

                now = datetime.now(timezone.utc)
                child_execution = Execution(
                    workflow_id=workflow.id,
                    user_id=workflow.user_id,
                    parent_execution_id=UUID(str(parent_execution_id)),
                    status="RUNNING",
                    triggered_by="execute_workflow",
                    started_at=now,
                    finished_at=None,
                    error_message=None,
                )
                session.add(child_execution)
                session.flush()

                node_rows: dict[str, NodeExecution] = {}

                def progress_callback(
                    *,
                    node_id: str,
                    node_type: str,
                    status: str,
                    input_data: Any = None,
                    output_data: Any = None,
                    error_message: str | None = None,
                ) -> None:
                    row = node_rows.get(node_id)
                    if row is None:
                        row = NodeExecution(
                            execution_id=child_execution.id,
                            node_id=node_id,
                            node_type=node_type,
                        )
                        session.add(row)
                        node_rows[node_id] = row
                    row.status = status
                    if input_data is not None:
                        row.input_data = input_data
                    if output_data is not None:
                        row.output_data = output_data
                    row.error_message = error_message
                    row.started_at = row.started_at or datetime.now(timezone.utc)
                    if status in {"SUCCEEDED", "FAILED", "SKIPPED", "BLOCKED"}:
                        row.finished_at = datetime.now(timezone.utc)
                    session.flush()

                resolved_credential_data = self._resolve_credential_data(
                    session=session,
                    definition=definition,
                    user_id=workflow.user_id,
                )
                resolved_credentials = {
                    credential_id: (
                        str(
                            token_data.get("api_key")
                            or token_data.get("bot_token")
                            or token_data.get("access_token")
                            or ""
                        )
                    )
                    for credential_id, token_data in resolved_credential_data.items()
                    if token_data.get("api_key")
                    or token_data.get("bot_token")
                    or token_data.get("access_token")
                }

                child_runner_context = {
                    **parent_runner_context,
                    "execution_id": child_execution.id,
                    "workflow_id": workflow.id,
                    "user_id": workflow.user_id,
                    "parent_execution_id": parent_execution_id,
                    "resolved_credentials": resolved_credentials,
                    "resolved_credential_data": resolved_credential_data,
                    "parallel_fanout_enabled": False,
                }

                try:
                    result = DagExecutor().execute_inline_child(
                        definition=definition,
                        initial_payload=payload,
                        runner_context=child_runner_context,
                        progress_callback=progress_callback,
                    )
                except NodeExecutionError as exc:
                    child_execution.status = "FAILED"
                    child_execution.finished_at = datetime.now(timezone.utc)
                    child_execution.error_message = exc.user_message
                    session.commit()
                    raise ValueError(exc.user_message) from exc
                except Exception as exc:
                    child_execution.status = "FAILED"
                    child_execution.finished_at = datetime.now(timezone.utc)
                    child_execution.error_message = str(exc)
                    session.commit()
                    raise

                terminal_output = self._terminal_output(result)
                child_execution.status = "SUCCEEDED"
                child_execution.finished_at = datetime.now(timezone.utc)
                child_execution.error_message = None
                session.commit()

                if isinstance(terminal_output, dict):
                    return {
                        **terminal_output,
                        "__child_execution": {
                            "execution_id": str(child_execution.id),
                            "status": child_execution.status,
                            "final_output": terminal_output,
                        },
                    }
                return {
                    "child_output": terminal_output,
                    "__child_execution": {
                        "execution_id": str(child_execution.id),
                        "status": child_execution.status,
                        "final_output": terminal_output,
                    },
                }
        finally:
            engine.dispose()

    @staticmethod
    def _to_sync_database_url(database_url: str) -> str:
        return (
            database_url.replace("+asyncpg", "+psycopg")
            if "+asyncpg" in database_url
            else database_url
        )

    @staticmethod
    def _resolve_child_workflow(
        *,
        session: Session,
        config: dict[str, Any],
        user_id: Any,
        parent_workflow_id: Any,
    ) -> tuple[Workflow, dict[str, Any]]:
        source = str(config.get("source") or "database").strip().lower()
        if source == "json":
            raw_definition = config.get("workflow_json")
            if isinstance(raw_definition, str):
                try:
                    definition = json.loads(raw_definition)
                except Exception as exc:
                    raise ValueError("ExecuteWorkflowRunner: workflow_json is not valid JSON") from exc
            elif isinstance(raw_definition, dict):
                definition = raw_definition
            else:
                raise ValueError("ExecuteWorkflowRunner: workflow_json is required")
            definition = ExecuteWorkflowRunner._normalize_workflow_definition(definition)

            if not parent_workflow_id:
                raise ValueError(
                    "ExecuteWorkflowRunner: parent workflow_id is required for inline JSON workflows"
                )
            workflow = session.scalar(
                select(Workflow).where(
                    Workflow.id == UUID(str(parent_workflow_id)),
                    Workflow.user_id == UUID(str(user_id)),
                )
            )
            if workflow is None:
                raise ValueError("ExecuteWorkflowRunner: parent workflow not found")
            return workflow, definition

        workflow_id = str(config.get("workflow_id") or "").strip()
        if not workflow_id:
            raise ValueError("ExecuteWorkflowRunner: workflow_id is required")
        workflow = session.scalar(
            select(Workflow).where(
                Workflow.id == UUID(workflow_id),
                Workflow.user_id == UUID(str(user_id)),
            )
        )
        if workflow is None:
            raise ValueError("ExecuteWorkflowRunner: child workflow not found")
        return workflow, ExecuteWorkflowRunner._normalize_workflow_definition(
            dict(workflow.definition or {})
        )

    @staticmethod
    def _normalize_workflow_definition(definition: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(definition, dict):
            raise ValueError("ExecuteWorkflowRunner: workflow definition must be a JSON object")

        raw_definition = definition
        if isinstance(raw_definition.get("definition"), dict):
            raw_definition = raw_definition["definition"]

        raw_nodes = raw_definition.get("nodes")
        raw_edges = raw_definition.get("edges")
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError(
                "ExecuteWorkflowRunner: workflow definition must contain nodes and edges arrays"
            )

        nodes: list[dict[str, Any]] = []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, dict):
                continue

            raw_data = raw_node.get("data") if isinstance(raw_node.get("data"), dict) else {}
            node_type = str(
                raw_node.get("type")
                or raw_data.get("type")
                or ""
            ).strip()
            if node_type in {"trigger", "action", "transform", "input_output", "utility", "ai"}:
                node_type = str(raw_data.get("type") or node_type).strip()

            node_id = str(raw_node.get("id") or "").strip()
            if not node_id:
                continue

            raw_config = raw_node.get("config")
            if not isinstance(raw_config, dict):
                raw_config = raw_data.get("config")
            if not isinstance(raw_config, dict):
                raw_config = {}

            label = raw_node.get("label")
            if not label:
                label = raw_data.get("label") or node_type

            position = raw_node.get("position")
            if not isinstance(position, dict):
                position = {"x": 0, "y": 0}

            nodes.append(
                {
                    "id": node_id,
                    "type": node_type,
                    "label": str(label or node_type),
                    "position": position,
                    "config": raw_config,
                }
            )

        edges: list[dict[str, Any]] = []
        for raw_edge in raw_edges:
            if not isinstance(raw_edge, dict):
                continue
            source = str(raw_edge.get("source") or "").strip()
            target = str(raw_edge.get("target") or "").strip()
            if not source or not target:
                continue
            edges.append(
                {
                    "id": str(raw_edge.get("id") or f"{source}->{target}"),
                    "source": source,
                    "target": target,
                    "sourceHandle": raw_edge.get("sourceHandle"),
                    "targetHandle": raw_edge.get("targetHandle"),
                    "branch": raw_edge.get("branch"),
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "loop_control": {
                "enabled": False,
                "max_node_executions": 3,
                "max_total_node_executions": 500,
                **(
                    raw_definition.get("loop_control")
                    if isinstance(raw_definition.get("loop_control"), dict)
                    else {}
                ),
            },
        }

    @staticmethod
    def _guard_circular_reference(
        *,
        definition: dict[str, Any],
        parent_workflow_id: Any,
    ) -> None:
        if not parent_workflow_id:
            return
        parent_id = str(parent_workflow_id)
        for node in definition.get("nodes", []):
            if not isinstance(node, dict) or node.get("type") != "execute_workflow":
                continue
            config = node.get("config") if isinstance(node.get("config"), dict) else {}
            if str(config.get("source") or "database") != "database":
                continue
            if str(config.get("workflow_id") or "") == parent_id:
                raise ValueError("Circular workflow reference detected")

    @staticmethod
    def _terminal_output(result: dict[str, Any]) -> Any:
        terminal_outputs = result.get("terminal_outputs")
        if isinstance(terminal_outputs, dict) and len(terminal_outputs) == 1:
            return next(iter(terminal_outputs.values()))
        if terminal_outputs:
            return terminal_outputs
        node_outputs = result.get("node_outputs")
        visited_nodes = result.get("visited_nodes")
        if isinstance(node_outputs, dict) and isinstance(visited_nodes, list) and visited_nodes:
            return node_outputs.get(visited_nodes[-1])
        return {}

    @staticmethod
    def _resolve_credential_data(
        *,
        session: Session,
        definition: dict[str, Any],
        user_id: Any,
    ) -> dict[str, dict[str, Any]]:
        credential_ids: set[str] = set()
        for node in definition.get("nodes", []):
            if not isinstance(node, dict):
                continue
            config = node.get("config") if isinstance(node.get("config"), dict) else {}
            credential_id = str(config.get("credential_id") or "").strip()
            if credential_id:
                credential_ids.add(credential_id)

        resolved: dict[str, dict[str, Any]] = {}
        for credential_id in credential_ids:
            try:
                row = session.get(AppCredential, UUID(credential_id))
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
                    "refresh_token",
                    "id_token",
                    "webhook_url",
                    "channel",
                }:
                    try:
                        decrypted[key] = decrypt_data(value)
                    except Exception:
                        decrypted[key] = value
                    continue
                decrypted[key] = value

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

            resolved[credential_id] = decrypted
        return resolved

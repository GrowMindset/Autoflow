from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import create_access_token
from app.core.database import get_db
from app.main import app
from app.models import Base
from app.models.credential import AppCredential
from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.user import User
from app.models.workflows import Workflow
from app.execution.runners.nodes.ai_agent import AIAgentRunner
from app.services.execution_service import ExecutionService
from app.tasks import execute_workflow as execute_workflow_tasks
from test.asgi_client import ASGITestClient


def _auth_headers(user_id: UUID) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id)})
    return {"authorization": f"Bearer {token}"}


class NodeExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            self.fail("DATABASE_URL is required to run tests")

        self.schema_name = f"node_test_{uuid4().hex}"
        self.admin_engine = create_async_engine(database_url, future=True)
        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema_name}"'))

        self.engine = create_async_engine(
            database_url,
            future=True,
            connect_args={"server_settings": {"search_path": self.schema_name}},
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self._original_task_session_factory = execute_workflow_tasks._create_task_session_factory

        def override_task_session_factory():
            return self.session_factory

        execute_workflow_tasks._create_task_session_factory = override_task_session_factory

        async def override_get_db():
            async with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        self.client = ASGITestClient(app)

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()
        execute_workflow_tasks._create_task_session_factory = self._original_task_session_factory
        await self.engine.dispose()
        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{self.schema_name}" CASCADE'))
        await self.admin_engine.dispose()

    async def _create_user(self, email: str) -> User:
        async with self.session_factory() as session:
            user = User(email=email, username=email.split("@")[0], hashed_password="pw")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def _create_workflow(self, user_id: UUID) -> Workflow:
        async with self.session_factory() as session:
            wf = Workflow(
                user_id=user_id,
                name="Test WF",
                definition={
                    "nodes": [
                        {
                            "id": "node_1",
                            "type": "datetime_format",
                            "config": {"format": "YYYY-MM-DD"},
                        }
                    ],
                    "edges": [],
                },
            )
            session.add(wf)
            await session.commit()
            await session.refresh(wf)
            return wf

    async def test_execute_node_creates_correct_records(self) -> None:
        user = await self._create_user("test@example.com")
        wf = await self._create_workflow(user.id)
        node_id = "node_1"

        status_code, payload = await self.client.post(
            f"/workflows/{wf.id}/nodes/{node_id}/execute",
            json_body={"input_data": {"date": "2024-01-01"}},
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 202)
        execution_id = UUID(payload["execution_id"])
        self.assertEqual(payload["triggered_by"], "datetime_format")

        # Verify DB records
        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.triggered_by, "datetime_format")

            node_exec_query = await session.execute(
                select(NodeExecution).where(NodeExecution.execution_id == execution_id)
            )
            node_execs = node_exec_query.scalars().all()
            self.assertEqual(len(node_execs), 1)
            self.assertEqual(node_execs[0].node_id, node_id)
            self.assertEqual(node_execs[0].node_type, "datetime_format")
            self.assertEqual(node_execs[0].input_data, {"date": "2024-01-01"})

    async def test_run_execution_resolves_ai_credentials_and_persists_output(self) -> None:
        user = await self._create_user("ai-node@example.com")
        credential_id = uuid4()

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="AI Workflow",
                definition={
                    "nodes": [
                        {
                            "id": "trigger",
                            "type": "manual_trigger",
                            "config": {},
                        },
                        {
                            "id": "agent",
                            "type": "ai_agent",
                            "config": {
                                "system_prompt": "You are replying to {{trigger.customer.name}} using {{chat_model.model}}.",
                                "command": "Reply to {{trigger.customer.name}} about {{trigger.customer.topic}}",
                            },
                        },
                        {
                            "id": "chat_cfg",
                            "type": "chat_model_openai",
                            "config": {
                                "credential_id": str(credential_id),
                                "model": "gpt-4o-mini",
                                "temperature": 0.25,
                                "max_tokens": 64,
                            },
                        },
                    ],
                    "edges": [
                        {"id": "e1", "source": "trigger", "target": "agent"},
                        {
                            "id": "e2",
                            "source": "chat_cfg",
                            "target": "agent",
                            "targetHandle": "chat_model",
                        },
                    ],
                },
            )
            session.add(workflow)
            await session.flush()
            session.add(
                AppCredential(
                    id=credential_id,
                    user_id=user.id,
                    app_name="openai",
                    token_data={"api_key": "encrypted-openai-token"},
                )
            )
            session.add(
                Execution(
                    workflow_id=workflow.id,
                    user_id=user.id,
                    status="PENDING",
                    triggered_by="manual",
                    started_at=None,
                    finished_at=None,
                    error_message=None,
                )
            )
            await session.commit()

            execution = await session.scalar(
                select(Execution).where(Execution.workflow_id == workflow.id)
            )
            self.assertIsNotNone(execution)
            execution_id = execution.id

        captured: dict[str, object] = {}

        def fake_call_openai(*args, **kwargs):
            provider = next((arg for arg in args if hasattr(arg, "api_key")), None)
            captured["api_key"] = getattr(provider, "api_key", None)
            captured["model"] = kwargs.get("model")
            captured["system_prompt"] = kwargs.get("system_prompt")
            captured["command"] = kwargs.get("command")
            captured["temperature"] = kwargs.get("temperature")
            captured["max_tokens"] = kwargs.get("max_tokens")
            return "AI says hello"

        with (
            patch("app.core.security.decrypt_data", return_value="decrypted-openai-key") as decrypt_mock,
            patch.object(AIAgentRunner, "_run_provider_completion", side_effect=fake_call_openai),
        ):
            await execute_workflow_tasks._run_execution(
                execution_id=str(execution_id),
                initial_payload={
                    "customer": {
                        "name": "Asha",
                        "topic": "order status",
                    }
                },
                start_node_id="trigger",
            )

        decrypt_mock.assert_called_once_with("encrypted-openai-token")
        self.assertEqual(captured["api_key"], "decrypted-openai-key")
        self.assertEqual(captured["model"], "gpt-4o-mini")
        self.assertEqual(
            captured["system_prompt"],
            "You are replying to Asha using gpt-4o-mini.",
        )
        self.assertEqual(
            captured["command"],
            "Reply to Asha about order status",
        )

        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.status, "SUCCEEDED")

            rows = (
                await session.execute(
                    select(NodeExecution)
                    .where(NodeExecution.execution_id == execution_id)
                    .order_by(NodeExecution.node_id)
                )
            ).scalars().all()

        rows_by_id = {row.node_id: row for row in rows}
        self.assertEqual(rows_by_id["trigger"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["agent"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["agent"].error_message, None)
        self.assertEqual(
            rows_by_id["agent"].input_data["chat_model"],
            {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "credential_id": str(credential_id),
                "api_key": "decrypted-openai-key",
                "options": {
                    "temperature": 0.25,
                    "max_tokens": 64,
                },
            },
        )
        self.assertEqual(
            rows_by_id["agent"].output_data,
            {
                "output": "AI says hello",
                "ai_metadata": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "system_prompt": "You are replying to Asha using gpt-4o-mini.",
                    "temperature": 0.25,
                },
            },
        )

    async def test_webhook_filter_ai_agent_telegram_execution_and_get_execution_output(self) -> None:
        user = await self._create_user("endtoend@example.com")
        credential_id = uuid4()

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="Webhook Filter AI Workflow",
                definition={
                    "nodes": [
                        {
                            "id": "trigger",
                            "type": "webhook_trigger",
                            "config": {},
                        },
                        {
                            "id": "filter",
                            "type": "filter",
                            "config": {
                                "input_key": "orders",
                                "field": "amount",
                                "operator": "greater_than",
                                "value": 100,
                            },
                        },
                        {
                            "id": "chat_cfg",
                            "type": "chat_model_openai",
                            "config": {
                                "credential_id": str(credential_id),
                                "model": "gpt-4o-mini",
                                "temperature": 0.1,
                                "max_tokens": 64,
                            },
                        },
                        {
                            "id": "agent",
                            "type": "ai_agent",
                            "config": {
                                "system_prompt": "Compose a short telegram summary of the filtered orders.",
                                "command": "Summarize the orders: {{filter.orders}}",
                            },
                        },
                        {
                            "id": "telegram",
                            "type": "telegram",
                            "config": {
                                "chat_id": "12345",
                                "message": "{{agent.output}}",
                            },
                        },
                    ],
                    "edges": [
                        {"id": "e1", "source": "trigger", "target": "filter"},
                        {
                            "id": "e2",
                            "source": "chat_cfg",
                            "target": "agent",
                            "targetHandle": "chat_model",
                        },
                        {"id": "e3", "source": "filter", "target": "agent"},
                        {"id": "e4", "source": "agent", "target": "telegram"},
                    ],
                },
            )
            session.add(workflow)
            await session.flush()
            session.add(
                AppCredential(
                    id=credential_id,
                    user_id=user.id,
                    app_name="openai",
                    token_data={"api_key": "encrypted-openai-token"},
                )
            )
            session.add(
                Execution(
                    workflow_id=workflow.id,
                    user_id=user.id,
                    status="PENDING",
                    triggered_by="webhook",
                    started_at=None,
                    finished_at=None,
                    error_message=None,
                )
            )
            await session.commit()
            await session.refresh(workflow)
            execution = await session.scalar(
                select(Execution).where(Execution.workflow_id == workflow.id)
            )
            self.assertIsNotNone(execution)
            execution_id = execution.id

        captured: dict[str, object] = {}

        def fake_call_openai(*args, **kwargs):
            provider = next((arg for arg in args if hasattr(arg, "api_key")), None)
            captured["api_key"] = getattr(provider, "api_key", None)
            captured["model"] = kwargs.get("model")
            captured["system_prompt"] = kwargs.get("system_prompt")
            captured["command"] = kwargs.get("command")
            captured["temperature"] = kwargs.get("temperature")
            captured["max_tokens"] = kwargs.get("max_tokens")
            return "AI summary of filtered orders"

        with (
            patch("app.core.security.decrypt_data", return_value="decrypted-openai-key"),
            patch.object(AIAgentRunner, "_run_provider_completion", side_effect=fake_call_openai),
        ):
            await execute_workflow_tasks._run_execution(
                execution_id=str(execution_id),
                initial_payload={
                    "orders": [
                        {"id": "o1", "amount": 50},
                        {"id": "o2", "amount": 200},
                    ],
                },
                start_node_id="trigger",
            )

        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.status, "SUCCEEDED")

            rows = (
                await session.execute(
                    select(NodeExecution).where(NodeExecution.execution_id == execution_id)
                )
            ).scalars().all()

        rows_by_id = {row.node_id: row for row in rows}
        self.assertEqual(rows_by_id["trigger"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["filter"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["agent"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["telegram"].status, "SUCCEEDED")

        self.assertEqual(
            rows_by_id["filter"].output_data,
            {
                "orders": [{"id": "o2", "amount": 200}],
                "triggered": True,
                "trigger_type": "webhook",
            },
        )
        self.assertEqual(
            rows_by_id["agent"].output_data,
            {
                "output": "AI summary of filtered orders",
                "ai_metadata": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "system_prompt": "Compose a short telegram summary of the filtered orders.",
                    "temperature": 0.1,
                },
            },
        )
        self.assertEqual(
            rows_by_id["telegram"].output_data,
            {
                "output": "AI summary of filtered orders",
                "ai_metadata": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "system_prompt": "Compose a short telegram summary of the filtered orders.",
                    "temperature": 0.1,
                },
                "dummy_node_executed": True,
                "dummy_node_type": "telegram",
                "dummy_node_message": "Dummy node executed for 'telegram'",
            },
        )

        status_code, payload = await self.client.get(
            f"/executions/{execution_id}",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(status_code, 200)
        node_results = {node["node_id"]: node for node in payload["node_results"]}
        self.assertEqual(node_results["agent"]["output_data"], rows_by_id["agent"].output_data)
        self.assertEqual(node_results["telegram"]["output_data"], rows_by_id["telegram"].output_data)

    async def test_run_execution_schedules_delay_resume_without_blocking_worker(self) -> None:
        user = await self._create_user("delay-resume@example.com")

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="Delay Resume Workflow",
                definition={
                    "nodes": [
                        {"id": "trigger", "type": "manual_trigger", "config": {}},
                        {"id": "delay_1", "type": "delay", "config": {"amount": "1", "unit": "days"}},
                        {"id": "echo_1", "type": "datetime_format", "config": {"field": "date", "output_format": "%Y-%m-%d"}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "trigger", "target": "delay_1"},
                        {"id": "e2", "source": "delay_1", "target": "echo_1"},
                    ],
                },
            )
            session.add(workflow)
            session.add(
                Execution(
                    workflow_id=workflow.id,
                    user_id=user.id,
                    status="PENDING",
                    triggered_by="manual",
                    started_at=None,
                    finished_at=None,
                    error_message=None,
                )
            )
            await session.commit()
            execution = await session.scalar(
                select(Execution).where(Execution.workflow_id == workflow.id)
            )
            self.assertIsNotNone(execution)
            execution_id = execution.id

        scheduled_jobs: list[dict[str, object]] = []

        def _capture_apply_async(**kwargs):
            scheduled_jobs.append(kwargs)
            return None

        with patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=_capture_apply_async):
            await execute_workflow_tasks._run_execution(
                execution_id=str(execution_id),
                initial_payload={"date": "2026-01-01"},
                start_node_id="trigger",
            )

        self.assertEqual(len(scheduled_jobs), 1)
        scheduled_kwargs = scheduled_jobs[0].get("kwargs") or {}
        self.assertEqual(scheduled_kwargs.get("execution_id"), str(execution_id))
        self.assertEqual(scheduled_kwargs.get("start_node_id"), "echo_1")
        self.assertTrue(bool(scheduled_kwargs.get("resume")))
        self.assertTrue(
            ("eta" in scheduled_jobs[0]) or ("countdown" in scheduled_jobs[0]),
            "Expected deferred schedule to use eta or countdown for delay resume",
        )

        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.status, "WAITING")

            rows = (
                await session.execute(
                    select(NodeExecution)
                    .where(NodeExecution.execution_id == execution_id)
                    .order_by(NodeExecution.node_id)
                )
            ).scalars().all()

        rows_by_id = {row.node_id: row for row in rows}
        self.assertEqual(rows_by_id["trigger"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["delay_1"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["echo_1"].status, "WAITING")

    async def test_run_execution_fans_out_parallel_branches_as_queued_jobs(self) -> None:
        user = await self._create_user("parallel-fanout@example.com")

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="Parallel Fanout Workflow",
                definition={
                    "nodes": [
                        {"id": "trigger", "type": "manual_trigger", "config": {}},
                        {"id": "branch_a", "type": "telegram", "config": {"credential_id": "", "message": "A"}},
                        {"id": "branch_b", "type": "slack_send_message", "config": {"credential_id": "", "message": "B"}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "trigger", "target": "branch_a"},
                        {"id": "e2", "source": "trigger", "target": "branch_b"},
                    ],
                },
            )
            session.add(workflow)
            session.add(
                Execution(
                    workflow_id=workflow.id,
                    user_id=user.id,
                    status="PENDING",
                    triggered_by="manual",
                    started_at=None,
                    finished_at=None,
                    error_message=None,
                )
            )
            await session.commit()
            execution = await session.scalar(
                select(Execution).where(Execution.workflow_id == workflow.id)
            )
            self.assertIsNotNone(execution)
            execution_id = execution.id

        scheduled_jobs: list[dict[str, object]] = []

        def _capture_apply_async(**kwargs):
            scheduled_jobs.append(kwargs)
            return None

        with patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=_capture_apply_async):
            await execute_workflow_tasks._run_execution(
                execution_id=str(execution_id),
                initial_payload=None,
                start_node_id="trigger",
            )

        self.assertEqual(len(scheduled_jobs), 2)
        target_nodes = {
            str((job.get("kwargs") or {}).get("start_node_id"))
            for job in scheduled_jobs
        }
        self.assertEqual(target_nodes, {"branch_a", "branch_b"})
        self.assertTrue(
            all("eta" not in job and "countdown" not in job for job in scheduled_jobs),
            "Immediate branch fanout should queue without delay scheduling",
        )

        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.status, "WAITING")

            rows = (
                await session.execute(
                    select(NodeExecution)
                    .where(NodeExecution.execution_id == execution_id)
                    .order_by(NodeExecution.node_id)
                )
            ).scalars().all()

        rows_by_id = {row.node_id: row for row in rows}
        self.assertEqual(rows_by_id["trigger"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["branch_a"].status, "QUEUED")
        self.assertEqual(rows_by_id["branch_b"].status, "QUEUED")

    async def test_run_execution_requeues_when_concurrency_guard_slot_is_unavailable(self) -> None:
        user = await self._create_user("concurrency-guard@example.com")

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="Concurrency Guard Workflow",
                definition={
                    "nodes": [
                        {"id": "trigger", "type": "manual_trigger", "config": {}},
                    ],
                    "edges": [],
                },
            )
            session.add(workflow)
            session.add(
                Execution(
                    workflow_id=workflow.id,
                    user_id=user.id,
                    status="PENDING",
                    triggered_by="manual",
                    started_at=None,
                    finished_at=None,
                    error_message=None,
                )
            )
            await session.commit()
            execution = await session.scalar(
                select(Execution).where(Execution.workflow_id == workflow.id)
            )
            self.assertIsNotNone(execution)
            execution_id = execution.id

        scheduled_jobs: list[dict[str, object]] = []

        def _capture_apply_async(**kwargs):
            scheduled_jobs.append(kwargs)
            return None

        class _DummyRedis:
            async def aclose(self) -> None:
                return None

        with (
            patch.object(execute_workflow_tasks, "WORKFLOW_MAX_PARALLEL_NODES", 1),
            patch.object(
                execute_workflow_tasks,
                "_create_redis_client",
                new=AsyncMock(return_value=_DummyRedis()),
            ),
            patch.object(
                execute_workflow_tasks,
                "_acquire_execution_inflight_slot",
                new=AsyncMock(return_value=False),
            ),
            patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=_capture_apply_async),
        ):
            await execute_workflow_tasks._run_execution(
                execution_id=str(execution_id),
                initial_payload=None,
                start_node_id="trigger",
                guard_retry_count=0,
            )

        self.assertEqual(len(scheduled_jobs), 1)
        queued_job = scheduled_jobs[0]
        self.assertEqual(queued_job.get("queue"), execute_workflow_tasks.WORKFLOW_EXECUTION_QUEUE)
        self.assertIn("countdown", queued_job)
        self.assertEqual((queued_job.get("kwargs") or {}).get("guard_retry_count"), 1)

        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.status, "WAITING")

            rows = (
                await session.execute(
                    select(NodeExecution).where(NodeExecution.execution_id == execution_id)
                )
            ).scalars().all()

        rows_by_id = {row.node_id: row for row in rows}
        self.assertEqual(rows_by_id["trigger"].status, "QUEUED")

    async def test_stale_recovery_keeps_waiting_executions_recoverable(self) -> None:
        user = await self._create_user("stale-recovery@example.com")
        old_started_at = datetime.now(timezone.utc) - timedelta(minutes=90)

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="Stale Recovery Workflow",
                definition={
                    "nodes": [
                        {"id": "trigger", "type": "manual_trigger", "config": {}},
                        {"id": "branch_a", "type": "telegram", "config": {"credential_id": "", "message": "A"}},
                        {"id": "branch_b", "type": "slack_send_message", "config": {"credential_id": "", "message": "B"}},
                    ],
                    "edges": [],
                },
            )
            session.add(workflow)
            await session.flush()

            execution = Execution(
                workflow_id=workflow.id,
                user_id=user.id,
                status="RUNNING",
                triggered_by="manual",
                started_at=old_started_at,
                finished_at=None,
                error_message=None,
            )
            session.add(execution)
            await session.flush()

            session.add_all(
                [
                    NodeExecution(
                        execution_id=execution.id,
                        node_id="trigger",
                        node_type="manual_trigger",
                        status="SUCCEEDED",
                        input_data=None,
                        output_data={},
                        error_message=None,
                        started_at=old_started_at,
                        finished_at=old_started_at,
                    ),
                    NodeExecution(
                        execution_id=execution.id,
                        node_id="branch_a",
                        node_type="telegram",
                        status="WAITING",
                        input_data={},
                        output_data=None,
                        error_message=None,
                        started_at=old_started_at,
                        finished_at=None,
                    ),
                    NodeExecution(
                        execution_id=execution.id,
                        node_id="branch_b",
                        node_type="slack_send_message",
                        status="RUNNING",
                        input_data={},
                        output_data=None,
                        error_message=None,
                        started_at=old_started_at,
                        finished_at=None,
                    ),
                ]
            )
            await session.commit()

            service = ExecutionService(session)
            await service._mark_stale_running_executions(user_id=user.id)

            refreshed_execution = await session.get(Execution, execution.id)
            self.assertIsNotNone(refreshed_execution)
            self.assertEqual(refreshed_execution.status, "WAITING")

            refreshed_rows = (
                await session.execute(
                    select(NodeExecution)
                    .where(NodeExecution.execution_id == execution.id)
                    .order_by(NodeExecution.node_id)
                )
            ).scalars().all()

        rows_by_id = {row.node_id: row for row in refreshed_rows}
        self.assertEqual(rows_by_id["branch_a"].status, "WAITING")
        self.assertEqual(rows_by_id["branch_b"].status, "QUEUED")

    async def test_deferred_merge_resume_accumulates_inputs_until_ready(self) -> None:
        user = await self._create_user("merge-resume@example.com")

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="Deferred Merge Resume Workflow",
                definition={
                    "nodes": [
                        {"id": "trigger", "type": "manual_trigger", "config": {}},
                        {"id": "delay_a", "type": "delay", "config": {"amount": "1", "unit": "days"}},
                        {"id": "delay_b", "type": "delay", "config": {"amount": "1", "unit": "days"}},
                        {"id": "merge_1", "type": "merge", "config": {}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "trigger", "target": "delay_a"},
                        {"id": "e2", "source": "trigger", "target": "delay_b"},
                        {"id": "e3", "source": "delay_a", "target": "merge_1"},
                        {"id": "e4", "source": "delay_b", "target": "merge_1"},
                    ],
                },
            )
            session.add(workflow)
            session.add(
                Execution(
                    workflow_id=workflow.id,
                    user_id=user.id,
                    status="PENDING",
                    triggered_by="manual",
                    started_at=None,
                    finished_at=None,
                    error_message=None,
                )
            )
            await session.commit()
            execution = await session.scalar(
                select(Execution).where(Execution.workflow_id == workflow.id)
            )
            self.assertIsNotNone(execution)
            execution_id = execution.id

        scheduled_jobs: list[dict[str, object]] = []

        def _capture_apply_async(**kwargs):
            scheduled_jobs.append(kwargs)
            return None

        with patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=_capture_apply_async):
            await execute_workflow_tasks._run_execution(
                execution_id=str(execution_id),
                initial_payload=None,
                start_node_id="trigger",
            )

        self.assertEqual(len(scheduled_jobs), 2)
        resume_jobs = [
            (job.get("kwargs") or {})
            for job in scheduled_jobs
            if str((job.get("kwargs") or {}).get("start_node_id")) == "merge_1"
        ]
        self.assertEqual(len(resume_jobs), 2)

        with patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=_capture_apply_async):
            await execute_workflow_tasks._run_execution(**resume_jobs[0])

        async with self.session_factory() as session:
            execution_mid = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution_mid)
            self.assertEqual(execution_mid.status, "WAITING")
            merge_mid = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.execution_id == execution_id,
                    NodeExecution.node_id == "merge_1",
                )
            )
            self.assertIsNotNone(merge_mid)
            self.assertEqual(merge_mid.status, "QUEUED")

        with patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=_capture_apply_async):
            await execute_workflow_tasks._run_execution(**resume_jobs[1])

        async with self.session_factory() as session:
            execution_done = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution_done)
            self.assertEqual(execution_done.status, "SUCCEEDED")
            merge_done = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.execution_id == execution_id,
                    NodeExecution.node_id == "merge_1",
                )
            )
            self.assertIsNotNone(merge_done)
            self.assertEqual(merge_done.status, "SUCCEEDED")

    async def test_deferred_merge_resume_preserves_runtime_state_when_late_branch_enqueues(self) -> None:
        user = await self._create_user("merge-late-branch@example.com")

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="Deferred Merge Late Branch Workflow",
                definition={
                    "nodes": [
                        {"id": "trigger", "type": "manual_trigger", "config": {}},
                        {"id": "delay_1", "type": "delay", "config": {"amount": "1", "unit": "days"}},
                        {"id": "late_passthrough", "type": "unimplemented_passthrough", "config": {}},
                        {"id": "merge_1", "type": "merge", "config": {}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "trigger", "target": "merge_1", "targetHandle": "input1"},
                        {"id": "e2", "source": "trigger", "target": "delay_1"},
                        {"id": "e3", "source": "delay_1", "target": "late_passthrough"},
                        {"id": "e4", "source": "late_passthrough", "target": "merge_1", "targetHandle": "input2"},
                    ],
                },
            )
            session.add(workflow)
            session.add(
                Execution(
                    workflow_id=workflow.id,
                    user_id=user.id,
                    status="PENDING",
                    triggered_by="manual",
                    started_at=None,
                    finished_at=None,
                    error_message=None,
                )
            )
            await session.commit()
            execution = await session.scalar(
                select(Execution).where(Execution.workflow_id == workflow.id)
            )
            self.assertIsNotNone(execution)
            execution_id = execution.id

        initial_jobs: list[dict[str, object]] = []

        def _capture_initial_apply_async(**kwargs):
            initial_jobs.append(kwargs)
            return None

        with patch.object(
            execute_workflow_tasks.run_execution,
            "apply_async",
            side_effect=_capture_initial_apply_async,
        ):
            await execute_workflow_tasks._run_execution(
                execution_id=str(execution_id),
                initial_payload=None,
                start_node_id="trigger",
            )

        self.assertEqual(len(initial_jobs), 2)
        initial_job_payloads = [job.get("kwargs") or {} for job in initial_jobs]
        merge_job_1 = next(
            job
            for job in initial_job_payloads
            if str(job.get("start_node_id")) == "merge_1"
        )
        late_node_job = next(
            job
            for job in initial_job_payloads
            if str(job.get("start_node_id")) == "late_passthrough"
        )

        with patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=lambda **kwargs: None):
            await execute_workflow_tasks._run_execution(**merge_job_1)

        async with self.session_factory() as session:
            merge_mid = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.execution_id == execution_id,
                    NodeExecution.node_id == "merge_1",
                )
            )
            self.assertIsNotNone(merge_mid)
            self.assertEqual(merge_mid.status, "QUEUED")
            merge_runtime_mid = (
                (merge_mid.output_data or {}).get("__runtime_merge_state")
                if isinstance(merge_mid.output_data, dict)
                else None
            )
            self.assertIsInstance(merge_runtime_mid, dict)
            self.assertEqual(int((merge_runtime_mid or {}).get("received_inputs") or 0), 1)

        late_jobs: list[dict[str, object]] = []

        def _capture_late_apply_async(**kwargs):
            late_jobs.append(kwargs)
            return None

        with patch.object(
            execute_workflow_tasks.run_execution,
            "apply_async",
            side_effect=_capture_late_apply_async,
        ):
            await execute_workflow_tasks._run_execution(**late_node_job)

        late_merge_jobs = [
            (job.get("kwargs") or {})
            for job in late_jobs
            if str((job.get("kwargs") or {}).get("start_node_id")) == "merge_1"
        ]
        self.assertEqual(len(late_merge_jobs), 1)

        async with self.session_factory() as session:
            merge_after_enqueue = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.execution_id == execution_id,
                    NodeExecution.node_id == "merge_1",
                )
            )
            self.assertIsNotNone(merge_after_enqueue)
            merge_runtime_after_enqueue = (
                (merge_after_enqueue.output_data or {}).get("__runtime_merge_state")
                if isinstance(merge_after_enqueue.output_data, dict)
                else None
            )
            self.assertIsInstance(merge_runtime_after_enqueue, dict)
            self.assertEqual(int((merge_runtime_after_enqueue or {}).get("received_inputs") or 0), 1)

        with patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=lambda **kwargs: None):
            await execute_workflow_tasks._run_execution(**late_merge_jobs[0])

        async with self.session_factory() as session:
            execution_done = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution_done)
            self.assertEqual(execution_done.status, "SUCCEEDED")
            merge_done = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.execution_id == execution_id,
                    NodeExecution.node_id == "merge_1",
                )
            )
            self.assertIsNotNone(merge_done)
            self.assertEqual(merge_done.status, "SUCCEEDED")

    async def test_merge_resume_accounts_failed_continue_on_error_parent_as_blocked(self) -> None:
        user = await self._create_user("merge-failed-continue-parent@example.com")

        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user.id,
                name="Merge Failed Continue Parent Workflow",
                definition={
                    "nodes": [
                        {
                            "id": "left_parent",
                            "type": "code",
                            "config": {
                                "language": "python",
                                "code": "raise RuntimeError('boom')",
                                "on_error": "continue",
                            },
                        },
                        {"id": "right_parent", "type": "unimplemented_right", "config": {}},
                        {"id": "merge_1", "type": "merge", "config": {"mode": "append"}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "left_parent", "target": "merge_1", "targetHandle": "input1"},
                        {"id": "e2", "source": "right_parent", "target": "merge_1", "targetHandle": "input2"},
                    ],
                },
            )
            session.add(workflow)
            await session.flush()

            execution = Execution(
                workflow_id=workflow.id,
                user_id=user.id,
                status="PENDING",
                triggered_by="manual",
                started_at=None,
                finished_at=None,
                error_message=None,
            )
            session.add(execution)
            await session.flush()

            now = datetime.now(timezone.utc)
            session.add_all(
                [
                    NodeExecution(
                        execution_id=execution.id,
                        node_id="left_parent",
                        node_type="code",
                        status="FAILED",
                        input_data={"from": "left"},
                        output_data={"from": "left"},
                        error_message="boom",
                        started_at=now,
                        finished_at=now,
                    ),
                    NodeExecution(
                        execution_id=execution.id,
                        node_id="right_parent",
                        node_type="unimplemented_right",
                        status="SUCCEEDED",
                        input_data={"from": "right"},
                        output_data={"from": "right"},
                        error_message=None,
                        started_at=now,
                        finished_at=now,
                    ),
                ]
            )
            await session.commit()
            execution_id = execution.id

        with patch.object(execute_workflow_tasks.run_execution, "apply_async", side_effect=lambda **kwargs: None):
            await execute_workflow_tasks._run_execution(
                execution_id=str(execution_id),
                initial_payload={"from": "right"},
                start_node_id="merge_1",
                start_target_handle="input2",
                resume=True,
                merge_source_node_id="right_parent",
            )

        async with self.session_factory() as session:
            execution_done = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution_done)
            self.assertEqual(execution_done.status, "SUCCEEDED")
            merge_done = await session.scalar(
                select(NodeExecution).where(
                    NodeExecution.execution_id == execution_id,
                    NodeExecution.node_id == "merge_1",
                )
            )
            self.assertIsNotNone(merge_done)
            self.assertEqual(merge_done.status, "SUCCEEDED")

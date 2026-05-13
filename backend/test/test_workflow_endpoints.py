from __future__ import annotations

import os
import unittest
from collections.abc import AsyncGenerator
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.auth import create_access_token
from app.core.database import get_db
from app.main import app
from app.models import Base
from app.models.executions import Execution
from app.models.nodes_executions import NodeExecution
from app.models.user import User
from app.models.workflows import Workflow
from app.models.workflow_versions import WorkflowVersion
from app.tasks import execute_workflow as execute_workflow_tasks
from test.asgi_client import ASGITestClient


def _auth_headers(user_id: UUID) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id)})
    return {"authorization": f"Bearer {token}"}


class WorkflowEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            self.fail("DATABASE_URL is required to run workflow endpoint tests")

        self.schema_name = f"workflow_test_{uuid4().hex}"
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

        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
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

    async def _create_user(
        self,
        *,
        email: str,
        username: str,
    ) -> User:
        async with self.session_factory() as session:
            user = User(email=email, username=username, hashed_password="not-used-in-tests")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def _create_workflow(
        self,
        *,
        user_id: UUID,
        name: str = "Workflow",
        description: str | None = "desc",
        definition: dict | None = None,
        is_published: bool = False,
    ) -> Workflow:
        async with self.session_factory() as session:
            workflow = Workflow(
                user_id=user_id,
                name=name,
                description=description,
                definition=definition
                or {
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "manual_trigger",
                            "label": "Start",
                            "position": {"x": 10, "y": 20},
                            "config": {},
                        }
                    ],
                    "edges": [],
                },
                is_published=is_published,
            )
            session.add(workflow)
            await session.commit()
            await session.refresh(workflow)
            return workflow

    async def test_auth_required_for_all_workflow_endpoints(self) -> None:
        workflow_id = uuid4()
        version_id = uuid4()

        for method, path, body in [
            ("POST", "/workflows", {"name": "A", "definition": {"nodes": [], "edges": []}}),
            ("GET", "/workflows", None),
            ("GET", f"/workflows/{workflow_id}", None),
            ("PUT", f"/workflows/{workflow_id}", {"name": "B"}),
            ("POST", f"/workflows/{workflow_id}/publish", None),
            ("POST", f"/workflows/{workflow_id}/unpublish", None),
            ("POST", f"/workflows/{workflow_id}/versions", None),
            ("GET", f"/workflows/{workflow_id}/versions", None),
            ("GET", f"/workflows/{workflow_id}/versions/{version_id}", None),
            ("POST", f"/workflows/{workflow_id}/restore/{version_id}", None),
            ("GET", f"/workflows/{workflow_id}/public-run-url", None),
            ("DELETE", f"/workflows/{workflow_id}", None),
        ]:
            if method == "POST":
                status_code, payload = await self.client.post(path, json_body=body)
            elif method == "GET" and body is None and path == "/workflows":
                status_code, payload = await self.client.get(path)
            elif method == "GET":
                status_code, payload = await self.client.get(path)
            elif method == "PUT":
                status_code, payload = await self.client.put(path, json_body=body)
            else:
                status_code, payload = await self.client.delete(path)

            self.assertEqual(status_code, 401)
            self.assertEqual(payload["detail"], "Invalid authentication credentials")

    async def test_create_workflow_returns_full_workflow_object(self) -> None:
        user = await self._create_user(email="create@example.com", username="create-user")

        status_code, payload = await self.client.post(
            "/workflows",
            json_body={
                "name": "Order Processing Workflow",
                "description": "Filters paid orders",
                "definition": {
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "manual_trigger",
                            "label": "Start",
                            "position": {"x": 100, "y": 150},
                            "config": {},
                        },
                        {
                            "id": "n2",
                            "type": "filter",
                            "label": "Filter",
                            "position": {"x": 300, "y": 150},
                            "config": {"input_key": "items"},
                        },
                    ],
                    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
                },
            },
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 201)
        self.assertEqual(payload["name"], "Order Processing Workflow")
        self.assertEqual(payload["description"], "Filters paid orders")
        self.assertEqual(payload["user_id"], str(user.id))
        self.assertFalse(payload["is_published"])
        self.assertEqual(payload["definition"]["edges"][0]["id"], "e1")
        self.assertIn("created_at", payload)
        self.assertIn("updated_at", payload)

    async def test_create_workflow_rejects_invalid_definition(self) -> None:
        user = await self._create_user(email="invalid@example.com", username="invalid-user")

        status_code, payload = await self.client.post(
            "/workflows",
            json_body={
                "name": "Broken Workflow",
                "definition": {
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "manual_trigger",
                            "label": "Start",
                            "position": {"x": 0, "y": 0},
                            "config": {},
                        }
                    ],
                    "edges": [{"id": "e1", "source": "n1", "target": "missing"}],
                },
            },
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 422)
        self.assertIn("unknown nodes", str(payload))

    async def test_list_workflows_paginates_and_filters_to_current_user(self) -> None:
        owner = await self._create_user(email="owner@example.com", username="owner-user")
        other = await self._create_user(email="other@example.com", username="other-user")

        await self._create_workflow(user_id=owner.id, name="First")
        await self._create_workflow(user_id=owner.id, name="Second")
        await self._create_workflow(user_id=other.id, name="Hidden")

        status_code, payload = await self.client.get(
            "/workflows?limit=1&offset=0",
            headers=_auth_headers(owner.id),
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["offset"], 0)
        self.assertIsNone(payload["next_cursor"])
        self.assertEqual(len(payload["workflows"]), 1)
        self.assertEqual(payload["workflows"][0]["user_id"], str(owner.id))
        self.assertNotIn("definition", payload["workflows"][0])

    async def test_get_workflow_returns_404_for_missing_and_unowned_workflows(self) -> None:
        owner = await self._create_user(email="get-owner@example.com", username="get-owner")
        other = await self._create_user(email="get-other@example.com", username="get-other")
        workflow = await self._create_workflow(user_id=other.id, name="Private")

        missing_status, missing_payload = await self.client.get(
            f"/workflows/{uuid4()}",
            headers=_auth_headers(owner.id),
        )
        self.assertEqual(missing_status, 404)
        self.assertEqual(missing_payload["detail"], "Workflow not found")

        hidden_status, hidden_payload = await self.client.get(
            f"/workflows/{workflow.id}",
            headers=_auth_headers(owner.id),
        )
        self.assertEqual(hidden_status, 404)
        self.assertEqual(hidden_payload["detail"], "Workflow not found")

    async def test_publish_endpoints_toggle_status(self) -> None:
        user = await self._create_user(email="publish@example.com", username="publish-user")
        workflow = await self._create_workflow(user_id=user.id, name="Publish Workflow")

        publish_status, publish_payload = await self.client.post(
            f"/workflows/{workflow.id}/publish",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(publish_status, 200)
        self.assertTrue(publish_payload["is_published"])

        unpublish_status, unpublish_payload = await self.client.post(
            f"/workflows/{workflow.id}/unpublish",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(unpublish_status, 200)
        self.assertFalse(unpublish_payload["is_published"])

    async def test_public_run_url_is_stable_and_reflects_publish_status(self) -> None:
        user = await self._create_user(
            email="public-run@example.com",
            username="public-run-user",
        )
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Public Run Workflow",
            is_published=True,
        )

        first_status, first_payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(first_status, 200)
        self.assertEqual(first_payload["method"], "GET")
        self.assertEqual(first_payload["path"], "published-run")
        self.assertTrue(first_payload["is_active"])
        self.assertIn("/webhook/", first_payload["url"])
        first_token = first_payload["path_token"]

        unpublish_status, _ = await self.client.post(
            f"/workflows/{workflow.id}/unpublish",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(unpublish_status, 200)

        second_status, second_payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(second_status, 200)
        self.assertEqual(second_payload["path_token"], first_token)
        self.assertFalse(second_payload["is_active"])

    async def test_public_run_url_returns_404_for_non_trigger_workflow(self) -> None:
        user = await self._create_user(
            email="no-trigger@example.com",
            username="no-trigger-user",
        )
        workflow = await self._create_workflow(
            user_id=user.id,
            name="No Trigger",
            definition={
                "nodes": [
                    {
                        "id": "filter_only",
                        "type": "filter",
                        "label": "Filter",
                        "position": {"x": 0, "y": 0},
                        "config": {"input_key": "items"},
                    }
                ],
                "edges": [],
            },
            is_published=True,
        )

        status_code, payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 404)
        self.assertEqual(payload["detail"], "No trigger found for public run URL")

    async def test_public_run_url_for_form_workflow_points_to_public_form_path(self) -> None:
        user = await self._create_user(
            email="public-form-url@example.com",
            username="public-form-url-user",
        )
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Public Form Workflow",
            is_published=True,
            definition={
                "nodes": [
                    {
                        "id": "form_start",
                        "type": "form_trigger",
                        "label": "Form Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "form_title": "Lead Form",
                            "fields": [
                                {"name": "email", "label": "Email", "type": "email", "required": True}
                            ],
                        },
                    }
                ],
                "edges": [],
            },
        )

        status_code, payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["method"], "GET")
        self.assertTrue(payload["path"].startswith("public/forms/"))
        self.assertIn("/public/forms/", payload["url"])
        self.assertEqual(payload["path_token"], payload["path"].split("/")[-1])

    async def test_public_run_url_for_form_prefers_request_origin_when_available(self) -> None:
        user = await self._create_user(
            email="public-form-origin@example.com",
            username="public-form-origin-user",
        )
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Public Form Origin Workflow",
            is_published=True,
            definition={
                "nodes": [
                    {
                        "id": "form_start",
                        "type": "form_trigger",
                        "label": "Form Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "fields": [
                                {"name": "email", "label": "Email", "type": "email", "required": True}
                            ],
                        },
                    }
                ],
                "edges": [],
            },
        )

        headers = _auth_headers(user.id)
        headers["origin"] = "http://localhost:5173"
        status_code, payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=headers,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(payload["url"].startswith("http://localhost:5173/public/forms/"))

    async def test_public_form_definition_and_submit_work_for_published_form_workflow(self) -> None:
        user = await self._create_user(
            email="public-form-submit@example.com",
            username="public-form-submit-user",
        )
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Public Form Submit Workflow",
            is_published=True,
            definition={
                "nodes": [
                    {
                        "id": "form_start",
                        "type": "form_trigger",
                        "label": "Form Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "form_title": "Contact Form",
                            "form_description": "Tell us about your request",
                            "fields": [
                                {"name": "email", "label": "Email", "type": "email", "required": True},
                                {"name": "message", "label": "Message", "type": "textarea", "required": True},
                            ],
                        },
                    }
                ],
                "edges": [],
            },
        )

        endpoint_status, endpoint_payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(endpoint_status, 200)
        token = endpoint_payload["path_token"]

        definition_status, definition_payload = await self.client.get(f"/public/forms/{token}")
        self.assertEqual(definition_status, 200)
        self.assertEqual(definition_payload["workflow_id"], str(workflow.id))
        self.assertEqual(definition_payload["path_token"], token)
        self.assertEqual(definition_payload["form_title"], "Contact Form")
        self.assertEqual(len(definition_payload["fields"]), 2)
        self.assertTrue(definition_payload["submit_url"].endswith(f"/public/forms/{token}/submit"))

        submit_status, submit_payload = await self.client.post(
            f"/public/forms/{token}/submit",
            json_body={
                "form_data": {
                    "email": "test@example.com",
                    "message": "Need more details",
                }
            },
        )
        self.assertEqual(submit_status, 202)
        self.assertEqual(submit_payload["message"], "Workflow execution enqueued")
        execution_id = UUID(submit_payload["execution_id"])

        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.workflow_id, workflow.id)
            self.assertEqual(execution.triggered_by, "form")

    async def test_public_form_endpoints_return_404_for_invalid_or_unpublished_tokens(self) -> None:
        invalid_get_status, _ = await self.client.get("/public/forms/not-a-valid-token")
        self.assertEqual(invalid_get_status, 404)

        invalid_submit_status, _ = await self.client.post(
            "/public/forms/not-a-valid-token/submit",
            json_body={"form_data": {"email": "x@example.com"}},
        )
        self.assertEqual(invalid_submit_status, 404)

        user = await self._create_user(
            email="public-form-unpublished@example.com",
            username="public-form-unpublished-user",
        )
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Form Unpublish Workflow",
            is_published=True,
            definition={
                "nodes": [
                    {
                        "id": "form_start",
                        "type": "form_trigger",
                        "label": "Form Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "fields": [
                                {"name": "email", "label": "Email", "type": "email", "required": True}
                            ],
                        },
                    }
                ],
                "edges": [],
            },
        )

        endpoint_status, endpoint_payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(endpoint_status, 200)
        token = endpoint_payload["path_token"]

        unpublish_status, _ = await self.client.post(
            f"/workflows/{workflow.id}/unpublish",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(unpublish_status, 200)

        unpublished_get_status, _ = await self.client.get(f"/public/forms/{token}")
        self.assertEqual(unpublished_get_status, 404)

        unpublished_submit_status, _ = await self.client.post(
            f"/public/forms/{token}/submit",
            json_body={"form_data": {"email": "x@example.com"}},
        )
        self.assertEqual(unpublished_submit_status, 404)

    async def test_public_form_submit_missing_required_fields_fails_execution(self) -> None:
        user = await self._create_user(
            email="public-form-required@example.com",
            username="public-form-required-user",
        )
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Form Required Workflow",
            is_published=True,
            definition={
                "nodes": [
                    {
                        "id": "form_start",
                        "type": "form_trigger",
                        "label": "Form Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "fields": [
                                {"name": "email", "label": "Email", "type": "email", "required": True}
                            ],
                        },
                    }
                ],
                "edges": [],
            },
        )

        endpoint_status, endpoint_payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(endpoint_status, 200)
        token = endpoint_payload["path_token"]

        submit_status, submit_payload = await self.client.post(
            f"/public/forms/{token}/submit",
            json_body={"form_data": {}},
        )
        self.assertEqual(submit_status, 202)
        execution_id = UUID(submit_payload["execution_id"])

        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.workflow_id, workflow.id)
            self.assertEqual(execution.triggered_by, "form")
            self.assertNotEqual(execution.status, "SUCCEEDED")

    async def test_published_token_webhook_allows_get_and_post_methods(self) -> None:
        user = await self._create_user(
            email="published-method@example.com",
            username="published-method-user",
        )
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Published Method Workflow",
            is_published=True,
        )

        endpoint_status, endpoint_payload = await self.client.get(
            f"/workflows/{workflow.id}/public-run-url",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(endpoint_status, 200)
        token = endpoint_payload["path_token"]

        get_status, get_payload = await self.client.get(f"/webhook/{token}")
        self.assertEqual(get_status, 202)
        self.assertEqual(get_payload["message"], "Workflow execution enqueued")

        post_status, post_payload = await self.client.post(f"/webhook/{token}")
        self.assertEqual(post_status, 202)
        self.assertEqual(post_payload["message"], "Workflow execution enqueued")

    async def test_update_workflow_partially_updates_and_checks_ownership(self) -> None:
        owner = await self._create_user(email="update-owner@example.com", username="update-owner")
        other = await self._create_user(email="update-other@example.com", username="update-other")
        workflow = await self._create_workflow(user_id=owner.id, name="Draft")
        private_workflow = await self._create_workflow(user_id=other.id, name="Private")

        status_code, payload = await self.client.put(
            f"/workflows/{workflow.id}",
            json_body={"description": None, "is_published": True},
            headers=_auth_headers(owner.id),
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["id"], str(workflow.id))
        self.assertIsNone(payload["description"])
        self.assertTrue(payload["is_published"])

        hidden_status, hidden_payload = await self.client.put(
            f"/workflows/{private_workflow.id}",
            json_body={"name": "Nope"},
            headers=_auth_headers(owner.id),
        )
        self.assertEqual(hidden_status, 404)
        self.assertEqual(hidden_payload["detail"], "Workflow not found")

    async def test_delete_workflow_cascades_related_execution_rows(self) -> None:
        user = await self._create_user(email="delete@example.com", username="delete-user")
        workflow = await self._create_workflow(user_id=user.id, name="To Delete")

        async with self.session_factory() as session:
            execution = Execution(
                workflow_id=workflow.id,
                user_id=user.id,
                triggered_by="manual",
                status="PENDING",
            )
            session.add(execution)
            await session.flush()

            session.add(
                NodeExecution(
                    execution_id=execution.id,
                    node_id="n1",
                    node_type="manual_trigger",
                    status="PENDING",
                )
            )
            await session.commit()

        status_code, payload = await self.client.delete(
            f"/workflows/{workflow.id}",
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["message"], "Workflow deleted successfully")

        async with self.session_factory() as session:
            workflow_count = await session.scalar(select(func.count()).select_from(Workflow))
            execution_count = await session.scalar(select(func.count()).select_from(Execution))
            node_execution_count = await session.scalar(
                select(func.count()).select_from(NodeExecution)
            )

        self.assertEqual(workflow_count, 0)
        self.assertEqual(execution_count, 0)
        self.assertEqual(node_execution_count, 0)

    async def test_delete_workflow_returns_404_for_missing_and_unowned_workflows(self) -> None:
        owner = await self._create_user(email="delete-owner@example.com", username="delete-owner")
        other = await self._create_user(email="delete-other@example.com", username="delete-other")
        workflow = await self._create_workflow(user_id=other.id, name="Private Delete")

        missing_status, missing_payload = await self.client.delete(
            f"/workflows/{uuid4()}",
            headers=_auth_headers(owner.id),
        )
        self.assertEqual(missing_status, 404)
        self.assertEqual(missing_payload["detail"], "Workflow not found")

        hidden_status, hidden_payload = await self.client.delete(
            f"/workflows/{workflow.id}",
            headers=_auth_headers(owner.id),
        )
        self.assertEqual(hidden_status, 404)
        self.assertEqual(hidden_payload["detail"], "Workflow not found")

    async def test_run_form_executes_form_filter_if_else_aggregate_workflow(self) -> None:
        user = await self._create_user(email="form@example.com", username="form-user")
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Form Execution Workflow",
            definition={
                "nodes": [
                    {
                        "id": "form_start",
                        "type": "form_trigger",
                        "label": "Form Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "fields": [
                                {"name": "customer_name", "required": True},
                                {"name": "items", "required": True},
                            ]
                        },
                    },
                    {
                        "id": "filter_paid",
                        "type": "filter",
                        "label": "Filter High Value",
                        "position": {"x": 200, "y": 0},
                        "config": {
                            "input_key": "items",
                            "field": "amount",
                            "operator": "greater_than",
                            "value": "500",
                        },
                    },
                    {
                        "id": "check_vip",
                        "type": "if_else",
                        "label": "Check VIP",
                        "position": {"x": 400, "y": 0},
                        "config": {
                            "field": "customer_name",
                            "operator": "equals",
                            "value": "Asha",
                        },
                    },
                    {
                        "id": "count_matches",
                        "type": "aggregate",
                        "label": "Count Matches",
                        "position": {"x": 600, "y": 0},
                        "config": {
                            "input_key": "items",
                            "operation": "count",
                            "output_key": "matched_count",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "form_start", "target": "filter_paid"},
                    {"id": "e2", "source": "filter_paid", "target": "check_vip"},
                    {
                        "id": "e3",
                        "source": "check_vip",
                        "target": "count_matches",
                        "branch": "true",
                    },
                ],
            },
        )

        form_data = {
            "customer_name": "Asha",
            "items": [
                {"id": "o1", "amount": 120},
                {"id": "o2", "amount": 875},
                {"id": "o3", "amount": 640},
            ],
        }

        status_code, payload = await self.client.post(
            f"/workflows/{workflow.id}/run-form",
            json_body={"form_data": form_data},
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 202)
        self.assertEqual(payload["workflow_id"], str(workflow.id))
        self.assertEqual(payload["triggered_by"], "form")
        execution_id = UUID(payload["execution_id"])

        async with self.session_factory() as session:
            execution = await session.get(Execution, execution_id)
            self.assertIsNotNone(execution)
            self.assertEqual(execution.status, "SUCCEEDED")
            self.assertEqual(execution.triggered_by, "form")

            rows = (
                await session.execute(
                    select(NodeExecution)
                    .where(NodeExecution.execution_id == execution_id)
                    .order_by(NodeExecution.node_id)
                )
            ).scalars().all()

        self.assertEqual(len(rows), 4)
        rows_by_id = {row.node_id: row for row in rows}

        expected_form_output = {
            "triggered": True,
            "trigger_type": "form",
            **form_data,
        }
        expected_filtered_output = {
            "triggered": True,
            "trigger_type": "form",
            "customer_name": "Asha",
            "items": [
                {"id": "o2", "amount": 875},
                {"id": "o3", "amount": 640},
            ],
        }
        expected_if_output = {
            **expected_filtered_output,
            "_branch": "true",
        }

        self.assertEqual(rows_by_id["form_start"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["form_start"].input_data, form_data)
        self.assertEqual(rows_by_id["form_start"].output_data, expected_form_output)

        self.assertEqual(rows_by_id["filter_paid"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["filter_paid"].input_data, expected_form_output)
        self.assertEqual(rows_by_id["filter_paid"].output_data, expected_filtered_output)

        self.assertEqual(rows_by_id["check_vip"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["check_vip"].input_data, expected_filtered_output)
        self.assertEqual(rows_by_id["check_vip"].output_data, expected_if_output)

        self.assertEqual(rows_by_id["count_matches"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["count_matches"].input_data, expected_filtered_output)
        self.assertEqual(
            rows_by_id["count_matches"].output_data,
            {"matched_count": 2},
        )

    async def test_run_workflow_accepts_selected_manual_start_node(self) -> None:
        user = await self._create_user(email="manual-start@example.com", username="manual-start")
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Multi Trigger Workflow",
            definition={
                "nodes": [
                    {
                        "id": "manual_a",
                        "type": "manual_trigger",
                        "label": "Manual A",
                        "position": {"x": 0, "y": 0},
                        "config": {},
                    },
                    {
                        "id": "manual_b",
                        "type": "manual_trigger",
                        "label": "Manual B",
                        "position": {"x": 0, "y": 180},
                        "config": {},
                    },
                    {
                        "id": "dummy_a",
                        "type": "custom_dummy_a",
                        "label": "Dummy A",
                        "position": {"x": 220, "y": 0},
                        "config": {},
                    },
                    {
                        "id": "dummy_b",
                        "type": "custom_dummy_b",
                        "label": "Dummy B",
                        "position": {"x": 220, "y": 180},
                        "config": {},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "manual_a", "target": "dummy_a"},
                    {"id": "e2", "source": "manual_b", "target": "dummy_b"},
                ],
            },
        )

        status_code, payload = await self.client.post(
            f"/workflows/{workflow.id}/run",
            json_body={"start_node_id": "manual_b"},
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 202)
        execution_id = UUID(payload["execution_id"])

        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(NodeExecution)
                    .where(NodeExecution.execution_id == execution_id)
                    .order_by(NodeExecution.node_id)
                )
            ).scalars().all()

        rows_by_id = {row.node_id: row for row in rows}
        self.assertEqual(rows_by_id["manual_b"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["dummy_b"].status, "SUCCEEDED")
        self.assertEqual(rows_by_id["manual_a"].status, "PENDING")
        self.assertEqual(rows_by_id["dummy_a"].status, "PENDING")

    async def test_run_workflow_rejects_invalid_selected_start_node(self) -> None:
        user = await self._create_user(email="invalid-start@example.com", username="invalid-start")
        workflow = await self._create_workflow(user_id=user.id)

        status_code, payload = await self.client.post(
            f"/workflows/{workflow.id}/run",
            json_body={"start_node_id": "missing_trigger"},
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 400)
        self.assertIn("Selected start node", str(payload.get("detail")))

    async def test_run_workflow_rejects_when_workflow_is_inactive(self) -> None:
        user = await self._create_user(email="inactive-run@example.com", username="inactive-run")
        workflow = await self._create_workflow(user_id=user.id)

        update_status, _update_payload = await self.client.put(
            f"/workflows/{workflow.id}",
            json_body={"is_active": False},
            headers=_auth_headers(user.id),
        )
        self.assertEqual(update_status, 200)

        status_code, payload = await self.client.post(
            f"/workflows/{workflow.id}/run",
            json_body={},
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(payload.get("detail"), "Workflow is inactive. Please activate workflow first.")

    async def test_run_form_rejects_when_workflow_is_inactive(self) -> None:
        user = await self._create_user(email="inactive-form@example.com", username="inactive-form")
        workflow = await self._create_workflow(
            user_id=user.id,
            definition={
                "nodes": [
                    {
                        "id": "form_start",
                        "type": "form_trigger",
                        "label": "Lead Form",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "fields": [
                                {"name": "name", "label": "Name", "type": "text", "required": True}
                            ]
                        },
                    }
                ],
                "edges": [],
            },
        )

        update_status, _update_payload = await self.client.put(
            f"/workflows/{workflow.id}",
            json_body={"is_active": False},
            headers=_auth_headers(user.id),
        )
        self.assertEqual(update_status, 200)

        status_code, payload = await self.client.post(
            f"/workflows/{workflow.id}/run-form",
            json_body={"form_data": {"name": "Asha"}},
            headers=_auth_headers(user.id),
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(payload.get("detail"), "Workflow is inactive. Please activate workflow first.")

    async def test_create_and_list_workflow_versions(self) -> None:
        user = await self._create_user(email="versions@example.com", username="versions-user")
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Versioned Workflow",
            definition={
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 0, "y": 0},
                        "config": {},
                    },
                    {
                        "id": "n2",
                        "type": "dummy",
                        "label": "Step A",
                        "position": {"x": 220, "y": 0},
                        "config": {},
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            },
        )

        first_status, first_payload = await self.client.post(
            f"/workflows/{workflow.id}/versions",
            json_body={"note": "Initial stable version"},
            headers=_auth_headers(user.id),
        )
        self.assertEqual(first_status, 201)
        self.assertEqual(first_payload["version_number"], 1)
        self.assertEqual(first_payload["note"], "Initial stable version")
        self.assertEqual(
            first_payload["snapshot_json"]["definition"]["nodes"][1]["label"],
            "Step A",
        )

        update_status, _update_payload = await self.client.put(
            f"/workflows/{workflow.id}",
            json_body={
                "definition": {
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "manual_trigger",
                            "label": "Start",
                            "position": {"x": 0, "y": 0},
                            "config": {},
                        },
                        {
                            "id": "n2",
                            "type": "dummy",
                            "label": "Step B",
                            "position": {"x": 220, "y": 0},
                            "config": {},
                        },
                    ],
                    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
                }
            },
            headers=_auth_headers(user.id),
        )
        self.assertEqual(update_status, 200)

        second_status, second_payload = await self.client.post(
            f"/workflows/{workflow.id}/versions",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(second_status, 201)
        self.assertEqual(second_payload["version_number"], 2)
        self.assertIsNone(second_payload["note"])

        list_status, list_payload = await self.client.get(
            f"/workflows/{workflow.id}/versions",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(list_status, 200)
        self.assertEqual([item["version_number"] for item in list_payload["versions"]], [2, 1])

    async def test_get_and_restore_workflow_version(self) -> None:
        user = await self._create_user(email="restore@example.com", username="restore-user")
        workflow = await self._create_workflow(
            user_id=user.id,
            name="Draft Name",
            description="Draft Description",
            definition={
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 0, "y": 0},
                        "config": {},
                    },
                    {
                        "id": "n2",
                        "type": "dummy",
                        "label": "Original Node",
                        "position": {"x": 220, "y": 0},
                        "config": {},
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            },
        )

        create_status, create_payload = await self.client.post(
            f"/workflows/{workflow.id}/versions",
            json_body={"note": "Snapshot before edits"},
            headers=_auth_headers(user.id),
        )
        self.assertEqual(create_status, 201)
        version_id = create_payload["id"]

        update_status, _update_payload = await self.client.put(
            f"/workflows/{workflow.id}",
            json_body={
                "name": "Edited Name",
                "description": "Edited Description",
                "definition": {
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "manual_trigger",
                            "label": "Start",
                            "position": {"x": 0, "y": 0},
                            "config": {},
                        },
                        {
                            "id": "n2",
                            "type": "dummy",
                            "label": "Edited Node",
                            "position": {"x": 220, "y": 0},
                            "config": {},
                        },
                    ],
                    "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
                },
            },
            headers=_auth_headers(user.id),
        )
        self.assertEqual(update_status, 200)

        get_status, get_payload = await self.client.get(
            f"/workflows/{workflow.id}/versions/{version_id}",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(get_status, 200)
        self.assertEqual(get_payload["version_number"], 1)
        self.assertEqual(
            get_payload["snapshot_json"]["definition"]["nodes"][1]["label"],
            "Original Node",
        )

        restore_status, restore_payload = await self.client.post(
            f"/workflows/{workflow.id}/restore/{version_id}",
            headers=_auth_headers(user.id),
        )
        self.assertEqual(restore_status, 200)
        self.assertEqual(restore_payload["name"], "Draft Name")
        self.assertEqual(restore_payload["description"], "Draft Description")
        self.assertEqual(
            restore_payload["definition"]["nodes"][1]["label"],
            "Original Node",
        )

    async def test_workflow_version_endpoints_enforce_ownership(self) -> None:
        owner = await self._create_user(email="owner-versions@example.com", username="owner-versions")
        other = await self._create_user(email="other-versions@example.com", username="other-versions")
        workflow = await self._create_workflow(user_id=owner.id, name="Private Workflow")

        create_status, create_payload = await self.client.post(
            f"/workflows/{workflow.id}/versions",
            headers=_auth_headers(owner.id),
        )
        self.assertEqual(create_status, 201)
        version_id = create_payload["id"]

        for path in [
            f"/workflows/{workflow.id}/versions",
            f"/workflows/{workflow.id}/versions/{version_id}",
        ]:
            status_code, payload = await self.client.get(path, headers=_auth_headers(other.id))
            self.assertEqual(status_code, 404)
            self.assertEqual(payload["detail"], "Workflow not found")

        restore_status, restore_payload = await self.client.post(
            f"/workflows/{workflow.id}/restore/{version_id}",
            headers=_auth_headers(other.id),
        )
        self.assertEqual(restore_status, 404)
        self.assertEqual(restore_payload["detail"], "Workflow not found")

        async with self.session_factory() as session:
            total_versions = await session.scalar(
                select(func.count())
                .select_from(WorkflowVersion)
                .where(WorkflowVersion.workflow_id == workflow.id)
            )
        self.assertEqual(int(total_versions or 0), 1)

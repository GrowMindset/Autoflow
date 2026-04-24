from __future__ import annotations

import unittest
from uuid import uuid4

from app.main import app
from app.models.user import User
from app.routers.ai import get_llm_service
from app.services.llm_service import GeneratedWorkflowResult, WorkflowGenerationError
from app.schemas.workflows import WorkflowDefinition
from test.asgi_client import ASGITestClient


class _SuccessfulLLMService:
    async def generate_workflow_definition(self, prompt: str):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 100, "y": 150},
                        "config": {},
                    },
                    {
                        "id": "n2",
                        "type": "telegram",
                        "label": "Send Telegram Message",
                        "position": {"x": 360, "y": 150},
                        "config": {"chat_id": "", "message": "Hello"},
                    },
                ],
                "edges": [
                    {
                        "id": "e1",
                        "source": "n1",
                        "target": "n2",
                        "sourceHandle": None,
                        "targetHandle": None,
                        "branch": None,
                    }
                ],
            }
        )
        return GeneratedWorkflowResult(definition=definition, name="Sample Workflow")


class _FailingLLMService:
    async def generate_workflow_definition(self, prompt: str):
        raise WorkflowGenerationError(
            "Could not generate a valid workflow from your prompt. Please try rephrasing."
        )


async def _override_current_user() -> User:
    return User(
        id=uuid4(),
        email="ai@example.com",
        username="ai-user",
        hashed_password="unused",
    )


class AIEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        app.dependency_overrides.clear()
        self.client = ASGITestClient(app)

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_generate_workflow_requires_authentication(self) -> None:
        status_code, payload = await self.client.post(
            "/ai/generate-workflow",
            json_body={"prompt": "Build me a workflow"},
        )

        self.assertEqual(status_code, 401)
        self.assertEqual(payload["detail"], "Invalid authentication credentials")

    async def test_generate_workflow_returns_definition(self) -> None:
        from app.core.auth import get_current_user

        async def override_llm_service() -> _SuccessfulLLMService:
            return _SuccessfulLLMService()

        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_llm_service] = override_llm_service

        status_code, payload = await self.client.post(
            "/ai/generate-workflow",
            json_body={"prompt": "Send a telegram message when I run manually"},
            headers={"authorization": "Bearer fake-token"},
        )

        self.assertEqual(status_code, 200)
        self.assertIn("definition", payload)
        self.assertEqual(payload["definition"]["nodes"][0]["type"], "manual_trigger")
        self.assertEqual(payload["definition"]["edges"][0]["source"], "n1")

    async def test_generate_workflow_returns_structured_422_error(self) -> None:
        from app.core.auth import get_current_user

        async def override_llm_service() -> _FailingLLMService:
            return _FailingLLMService()

        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_llm_service] = override_llm_service

        status_code, payload = await self.client.post(
            "/ai/generate-workflow",
            json_body={"prompt": "Build something impossible"},
            headers={"authorization": "Bearer fake-token"},
        )

        self.assertEqual(status_code, 422)
        self.assertEqual(payload["detail"]["code"], "workflow_generation_failed")
        self.assertIn("Please try rephrasing", payload["detail"]["message"])

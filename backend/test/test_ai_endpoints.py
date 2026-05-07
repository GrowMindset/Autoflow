from __future__ import annotations

import unittest
from uuid import uuid4

from app.main import app
from app.models.user import User
from app.routers.ai import get_ai_chat_history_service, get_llm_service
from app.services.ai_chat_history_service import AIChatHistoryStorageUnavailableError
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

    async def assist_workflow(
        self,
        *,
        prompt: str,
        interaction_mode: str = "build",
        current_definition: WorkflowDefinition | None = None,
        conversation_state: dict | None = None,
    ) -> dict:
        if interaction_mode == "ask":
            return {
                "mode": "ask",
                "assistant_message": "Use webhook_trigger for incoming API events and map fields with {{...}} templates.",
                "questions": [],
                "assumptions": [],
                "definition": None,
                "name": None,
                "change_summary": None,
            }
        generated = await self.generate_workflow_definition(prompt)
        return {
            "mode": "generate",
            "assistant_message": "Workflow generated from your request.",
            "questions": [],
            "assumptions": [],
            "definition": generated.definition,
            "name": generated.name,
            "change_summary": None,
        }


class _FailingLLMService:
    async def generate_workflow_definition(self, prompt: str):
        raise WorkflowGenerationError(
            "Could not generate a valid workflow from your prompt. Please try rephrasing."
        )

    async def assist_workflow(
        self,
        *,
        prompt: str,
        interaction_mode: str = "build",
        current_definition: WorkflowDefinition | None = None,
        conversation_state: dict | None = None,
    ) -> dict:
        raise WorkflowGenerationError(
            "Could not generate a valid workflow from your prompt. Please try rephrasing."
        )


class _InMemoryAIHistoryService:
    def __init__(self) -> None:
        self.storage: dict[tuple[str, str], dict] = {}

    async def get_scope_history(self, *, user_id, scope_key: str):
        key = (str(user_id), scope_key)
        payload = self.storage.get(key, {"messages": [], "conversation_state": {}})
        return {
            "scope_key": scope_key,
            "messages": list(payload.get("messages", [])),
            "conversation_state": dict(payload.get("conversation_state", {})),
        }

    async def save_scope_history(self, *, user_id, scope_key: str, messages, conversation_state):
        key = (str(user_id), scope_key)
        payload = {
            "messages": list(messages or []),
            "conversation_state": dict(conversation_state or {}),
        }
        self.storage[key] = payload
        return {
            "scope_key": scope_key,
            "messages": payload["messages"],
            "conversation_state": payload["conversation_state"],
        }

    async def clear_scope_history(self, *, user_id, scope_key: str):
        key = (str(user_id), scope_key)
        existed = key in self.storage
        self.storage.pop(key, None)
        return {"deleted_messages": 1 if existed else 0, "deleted_states": 1 if existed else 0}

    async def clear_all_history(self, *, user_id):
        user_prefix = str(user_id)
        keys_to_delete = [key for key in self.storage if key[0] == user_prefix]
        for key in keys_to_delete:
            self.storage.pop(key, None)
        count = len(keys_to_delete)
        return {"deleted_messages": count, "deleted_states": count}


class _UnavailableAIHistoryService:
    async def get_scope_history(self, *, user_id, scope_key: str):
        raise AIChatHistoryStorageUnavailableError(
            "AI chat history storage is not initialized. Run database migrations: `alembic upgrade head`."
        )

    async def save_scope_history(self, *, user_id, scope_key: str, messages, conversation_state):
        raise AIChatHistoryStorageUnavailableError(
            "AI chat history storage is not initialized. Run database migrations: `alembic upgrade head`."
        )

    async def clear_scope_history(self, *, user_id, scope_key: str):
        raise AIChatHistoryStorageUnavailableError(
            "AI chat history storage is not initialized. Run database migrations: `alembic upgrade head`."
        )

    async def clear_all_history(self, *, user_id):
        raise AIChatHistoryStorageUnavailableError(
            "AI chat history storage is not initialized. Run database migrations: `alembic upgrade head`."
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
        self.history_service = _InMemoryAIHistoryService()

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

    async def test_workflow_assistant_requires_authentication(self) -> None:
        status_code, payload = await self.client.post(
            "/ai/workflow-assistant",
            json_body={"prompt": "Build me a workflow"},
        )

        self.assertEqual(status_code, 401)
        self.assertEqual(payload["detail"], "Invalid authentication credentials")

    async def test_workflow_assistant_returns_structured_response(self) -> None:
        from app.core.auth import get_current_user

        async def override_llm_service() -> _SuccessfulLLMService:
            return _SuccessfulLLMService()

        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_llm_service] = override_llm_service

        status_code, payload = await self.client.post(
            "/ai/workflow-assistant",
            json_body={
                "prompt": "Send a telegram message when I run manually",
                "conversation_state": {
                    "confirmed_choices": {},
                    "assumptions": [],
                },
            },
            headers={"authorization": "Bearer fake-token"},
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["mode"], "generate")
        self.assertIn("definition", payload)
        self.assertEqual(payload["definition"]["nodes"][0]["type"], "manual_trigger")

    async def test_workflow_assistant_supports_ask_interaction_mode(self) -> None:
        from app.core.auth import get_current_user

        async def override_llm_service() -> _SuccessfulLLMService:
            return _SuccessfulLLMService()

        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_llm_service] = override_llm_service

        status_code, payload = await self.client.post(
            "/ai/workflow-assistant",
            json_body={
                "prompt": "Which trigger should I use for incoming support ticket API payloads?",
                "interaction_mode": "ask",
                "conversation_state": {
                    "confirmed_choices": {},
                    "assumptions": [],
                },
            },
            headers={"authorization": "Bearer fake-token"},
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["mode"], "ask")
        self.assertIsNone(payload["definition"])
        self.assertIn("webhook_trigger", payload["assistant_message"])

    async def test_workflow_assistant_returns_422_error_shape(self) -> None:
        from app.core.auth import get_current_user

        async def override_llm_service() -> _FailingLLMService:
            return _FailingLLMService()

        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_llm_service] = override_llm_service

        status_code, payload = await self.client.post(
            "/ai/workflow-assistant",
            json_body={"prompt": "Build impossible workflow"},
            headers={"authorization": "Bearer fake-token"},
        )

        self.assertEqual(status_code, 422)
        self.assertEqual(payload["detail"]["code"], "workflow_generation_failed")
        self.assertEqual(payload["detail"]["mode"], "clarify")
        self.assertIn("Please try rephrasing", payload["detail"]["message"])

    async def test_chat_history_endpoints_round_trip_and_clear(self) -> None:
        from app.core.auth import get_current_user

        fixed_user = User(
            id=uuid4(),
            email="history@example.com",
            username="history-user",
            hashed_password="unused",
        )

        async def override_fixed_user() -> User:
            return fixed_user

        async def override_history_service() -> _InMemoryAIHistoryService:
            return self.history_service

        app.dependency_overrides[get_current_user] = override_fixed_user
        app.dependency_overrides[get_ai_chat_history_service] = override_history_service

        upsert_status, upsert_payload = await self.client.put(
            "/ai/chat-history/new",
            json_body={
                "messages": [
                    {
                        "id": "1",
                        "role": "user",
                        "content": "Build a workflow",
                        "timestamp": "2026-04-27T12:00:00Z",
                    },
                    {
                        "id": "2",
                        "role": "assistant",
                        "content": "Sure, generating it.",
                        "timestamp": "2026-04-27T12:00:05Z",
                        "mode": "generate",
                    },
                ],
                "conversation_state": {"lastMode": "generate"},
            },
            headers={"authorization": "Bearer fake-token"},
        )
        self.assertEqual(upsert_status, 200)
        self.assertEqual(upsert_payload["scope_key"], "new")
        self.assertEqual(len(upsert_payload["messages"]), 2)

        get_status, get_payload = await self.client.get(
            "/ai/chat-history/new",
            headers={"authorization": "Bearer fake-token"},
        )
        self.assertEqual(get_status, 200)
        self.assertEqual(get_payload["scope_key"], "new")
        self.assertEqual(get_payload["messages"][1]["role"], "assistant")
        self.assertEqual(get_payload["conversation_state"]["lastMode"], "generate")

        clear_scope_status, clear_scope_payload = await self.client.delete(
            "/ai/chat-history/new",
            headers={"authorization": "Bearer fake-token"},
        )
        self.assertEqual(clear_scope_status, 200)
        self.assertEqual(clear_scope_payload["message"], "AI chat history cleared for scope.")

        clear_all_status, clear_all_payload = await self.client.delete(
            "/ai/chat-history",
            headers={"authorization": "Bearer fake-token"},
        )
        self.assertEqual(clear_all_status, 200)
        self.assertEqual(clear_all_payload["message"], "All AI chat history cleared.")

    async def test_chat_history_returns_503_when_storage_is_unavailable(self) -> None:
        from app.core.auth import get_current_user

        async def override_history_service() -> _UnavailableAIHistoryService:
            return _UnavailableAIHistoryService()

        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[get_ai_chat_history_service] = override_history_service

        status_code, payload = await self.client.get(
            "/ai/chat-history/new",
            headers={"authorization": "Bearer fake-token"},
        )

        self.assertEqual(status_code, 503)
        self.assertEqual(payload["detail"]["code"], "ai_chat_history_unavailable")
        self.assertIn("alembic upgrade head", payload["detail"]["message"])

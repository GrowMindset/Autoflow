from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas.workflows import NODE_CONFIG_DEFAULTS
from app.services.llm_service import LLMService, WorkflowGenerationError


def _valid_definition() -> dict:
    return {
        "nodes": [
            {
                "id": "n1",
                "type": "manual_trigger",
                "label": "Manual Trigger",
                "position": {"x": 100, "y": 120},
                "config": {},
            },
            {
                "id": "n2",
                "type": "telegram",
                "label": "Send Telegram Message",
                "position": {"x": 340, "y": 120},
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


def _definition_for_prompt_kind(kind: str) -> dict:
    if kind == "webhook_telegram":
        return {
            "nodes": [
                {
                    "id": "n1",
                    "type": "webhook_trigger",
                    "label": "Webhook Trigger",
                    "position": {"x": 100, "y": 150},
                    "config": {},
                },
                {
                    "id": "n2",
                    "type": "telegram",
                    "label": "Send Telegram Message",
                    "position": {"x": 360, "y": 150},
                    "config": {"chat_id": "", "message": ""},
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
    if kind == "manual_if_else_telegram":
        return {
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
                    "type": "if_else",
                    "label": "Check Status",
                    "position": {"x": 360, "y": 150},
                    "config": {
                        "field": "status",
                        "operator": "equals",
                        "value": "active",
                    },
                },
                {
                    "id": "n3",
                    "type": "telegram",
                    "label": "Send Telegram Message",
                    "position": {"x": 620, "y": 150},
                    "config": {"chat_id": "", "message": ""},
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
            ],
        }
    if kind == "form_filter":
        return {
            "nodes": [
                {
                    "id": "n1",
                    "type": "form_trigger",
                    "label": "Form Trigger",
                    "position": {"x": 100, "y": 150},
                    "config": {
                        "form_title": "Contact Form",
                        "form_description": "",
                        "fields": [
                            {
                                "name": "email",
                                "label": "Email",
                                "type": "email",
                                "required": True,
                            }
                        ],
                    },
                },
                {
                    "id": "n2",
                    "type": "filter",
                    "label": "Filter Items",
                    "position": {"x": 360, "y": 150},
                    "config": {
                        "input_key": "items",
                        "field": "status",
                        "operator": "equals",
                        "value": "active",
                    },
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
    raise ValueError(f"Unknown prompt kind: {kind}")


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content)
                )
            ]
        )


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.completions = _FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


class LLMServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_system_prompt_contains_full_node_type_list_and_rules(self) -> None:
        prompt = LLMService.build_workflow_generation_system_prompt()

        for node_type in NODE_CONFIG_DEFAULTS:
            self.assertIn(f"- {node_type}", prompt)

        self.assertIn("Return ONLY one valid JSON object.", prompt)
        self.assertIn('Edges leaving if_else must set branch to "true" or "false".', prompt)
        self.assertIn("Edges leaving switch must set branch to a case label", prompt)

    def test_validate_generated_workflow_accepts_definition_wrapper(self) -> None:
        raw_content = json.dumps({"definition": _valid_definition()})

        definition = LLMService.validate_generated_workflow(raw_content)

        self.assertEqual(len(definition.nodes), 2)
        self.assertEqual(definition.nodes[1].type, "telegram")

    def test_validate_generated_workflow_rejects_unknown_node_type(self) -> None:
        payload = _valid_definition()
        payload["nodes"][1]["type"] = "slack"

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertIn("unsupported node types", str(context.exception))

    def test_validate_generated_workflow_requires_if_else_branch_labels(self) -> None:
        payload = {
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
                    "type": "if_else",
                    "label": "Check",
                    "position": {"x": 250, "y": 0},
                    "config": {
                        "field": "status",
                        "operator": "equals",
                        "value": "active",
                    },
                },
                {
                    "id": "n3",
                    "type": "telegram",
                    "label": "Notify",
                    "position": {"x": 500, "y": 0},
                    "config": {"chat_id": "", "message": ""},
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertIn("if_else edges must use branch", str(context.exception))

    def test_validate_generated_workflow_rejects_non_existent_edge_source_cleanly(self) -> None:
        payload = _valid_definition()
        payload["edges"][0]["source"] = "missing_node"

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertIn("non-existent source node", str(context.exception))

    def test_validate_generated_workflow_rejects_non_existent_edge_target_cleanly(self) -> None:
        payload = _valid_definition()
        payload["edges"][0]["target"] = "missing_node"

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertIn("targets non-existent node", str(context.exception))

    async def test_generate_workflow_definition_fails_lazily_without_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            service = LLMService(model="test-model")

            with self.assertRaises(WorkflowGenerationError) as context:
                await service.generate_workflow_definition("Build me a workflow")

        self.assertIn("OPENAI_API_KEY is not set", str(context.exception))

    async def test_generate_workflow_definition_retries_once_after_invalid_json(self) -> None:
        fake_client = _FakeClient(
            responses=[
                '{"definition": {"nodes": [',
                json.dumps({"definition": _valid_definition()}),
            ]
        )
        service = LLMService(client=fake_client, model="test-model", max_retries=1)

        definition = await service.generate_workflow_definition(
            "Send a telegram message when I manually run the workflow"
        )

        self.assertEqual(definition.nodes[1].type, "telegram")
        self.assertEqual(len(fake_client.completions.calls), 2)
        self.assertEqual(
            fake_client.completions.calls[0]["response_format"],
            {"type": "json_object"},
        )

    async def test_known_prompts_produce_expected_node_types(self) -> None:
        cases = [
            (
                "Send a Telegram message whenever a webhook is received",
                "webhook_telegram",
                {"webhook_trigger", "telegram"},
            ),
            (
                "When I run the workflow manually, check if status is active and then notify on Telegram",
                "manual_if_else_telegram",
                {"manual_trigger", "if_else", "telegram"},
            ),
            (
                "Create a form-based workflow that filters active items",
                "form_filter",
                {"form_trigger", "filter"},
            ),
        ]

        for prompt, definition_kind, expected_node_types in cases:
            fake_client = _FakeClient(
                responses=[json.dumps({"definition": _definition_for_prompt_kind(definition_kind)})]
            )
            service = LLMService(client=fake_client, model="test-model")

            definition = await service.generate_workflow_definition(prompt)

            actual_node_types = {node.type for node in definition.nodes}
            self.assertTrue(
                expected_node_types.issubset(actual_node_types),
                msg=f"Prompt {prompt!r} produced node types {actual_node_types}, expected at least {expected_node_types}",
            )

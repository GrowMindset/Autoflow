from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.workflows import NODE_CONFIG_DEFAULTS, WorkflowDefinition
from app.services.llm_service import (
    GeneratedWorkflowResult,
    LLMService,
    SUB_WORKFLOW_RESPONSE_MESSAGE,
    WorkflowGenerationError,
)


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
    if kind == "manual_ai_agent_openai":
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
                    "type": "ai_agent",
                    "label": "Draft Reply",
                    "position": {"x": 360, "y": 150},
                    "config": {
                        "system_prompt": "You are a helpful support assistant.",
                        "command": "Reply to {{customer.message}}",
                    },
                },
                {
                    "id": "n3",
                    "type": "chat_model_openai",
                    "label": "OpenAI Chat Model",
                    "position": {"x": 360, "y": 330},
                    "config": {
                        "credential_id": "",
                        "model": "gpt-4o",
                        "temperature": 0.7,
                        "max_tokens": None,
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
                },
                {
                    "id": "e2",
                    "source": "n3",
                    "target": "n2",
                    "sourceHandle": None,
                    "targetHandle": "chat_model",
                    "branch": None,
                },
            ],
        }
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
    if kind == "manual_image_linkedin":
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
                    "type": "image_gen",
                    "label": "Generate Image",
                    "position": {"x": 360, "y": 150},
                    "config": {
                        "credential_id": "",
                        "model": "dall-e-3",
                        "prompt": "Create a polished product launch image for {{topic}}.",
                        "size": "1024x1024",
                        "quality": "standard",
                        "style": "vivid",
                    },
                },
                {
                    "id": "n3",
                    "type": "linkedin",
                    "label": "Post To LinkedIn",
                    "position": {"x": 620, "y": 150},
                    "config": {
                        "credential_id": "",
                        "post_text": "Launching {{topic}}",
                        "image": "{{n2.image_base64}}",
                        "visibility": "PUBLIC",
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
                },
                {
                    "id": "e2",
                    "source": "n2",
                    "target": "n3",
                    "sourceHandle": None,
                    "targetHandle": None,
                    "branch": None,
                },
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
        self.assertIn("Edges leaving switch must set branch to a case id", prompt)
        self.assertIn('targetHandle to "chat_model"', prompt)
        self.assertIn("If the user asks to generate or include an AI-created image/visual", prompt)
        self.assertIn("Outputs available to later nodes: image_base64, image_url", prompt)
        self.assertIn("execute_workflow node with config.source=\"database\"", prompt)
        self.assertIn("Never generate both parent and child in a single definition", prompt)

    def test_validate_generated_workflow_accepts_definition_wrapper(self) -> None:
        raw_content = json.dumps({"definition": _valid_definition()})

        definition, _ = LLMService.validate_generated_workflow(raw_content)

        self.assertEqual(len(definition.nodes), 2)
        self.assertEqual(definition.nodes[1].type, "telegram")

    async def test_generate_workflow_definition_sub_workflow_returns_parent_message(self) -> None:
        payload = {
            "definition": {
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
                        "type": "execute_workflow",
                        "label": "Run Child Workflow",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            "source": "database",
                            "workflow_id": "",
                            "workflow_json": "",
                            "workflow_inputs": [{"key": "email", "value": "{{email}}"}],
                            "mode": "run_once",
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
            },
            "message": "ignored because backend enforces the exact message",
        }
        service = LLMService(client=_FakeClient([json.dumps(payload)]))

        result = await service.generate_workflow_definition(
            "When I run manually, call a sub-workflow with the email input."
        )

        self.assertEqual(result.message, SUB_WORKFLOW_RESPONSE_MESSAGE)
        self.assertEqual(result.definition.nodes[1].type, "execute_workflow")
        self.assertEqual(result.definition.nodes[1].config["workflow_id"], "")

    async def test_generate_workflow_definition_sub_workflow_falls_back_to_parent_wrapper(self) -> None:
        child_payload = {
            "nodes": [
                {
                    "id": "n1",
                    "type": "workflow_trigger",
                    "label": "Workflow Trigger",
                    "position": {"x": 100, "y": 120},
                    "config": {
                        "input_data_mode": "accept_all",
                        "input_schema": [],
                        "json_example": "",
                    },
                },
                {
                    "id": "n2",
                    "type": "telegram",
                    "label": "Send Telegram Message",
                    "position": {"x": 340, "y": 120},
                    "config": {"credential_id": "", "message": "{{data}}", "parse_mode": ""},
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
        service = LLMService(
            client=_FakeClient([json.dumps(child_payload), json.dumps(child_payload)])
        )

        result = await service.generate_workflow_definition(
            "Create a workflow where a webhook receives data and calls a sub-workflow to send a Telegram message with that data"
        )

        node_types = [node.type for node in result.definition.nodes]
        self.assertEqual(node_types, ["webhook_trigger", "execute_workflow"])
        self.assertEqual(result.definition.nodes[1].config["workflow_id"], "")
        self.assertEqual(result.message, SUB_WORKFLOW_RESPONSE_MESSAGE)

    def test_sub_workflow_parent_trigger_selection_prefers_prompt_trigger(self) -> None:
        cases = [
            ("webhook receives data and calls a sub-workflow", "webhook_trigger"),
            ("API POST calls a child workflow", "webhook_trigger"),
            ("user submits a form then runs a child workflow", "form_trigger"),
            ("daily schedule runs another workflow", "schedule_trigger"),
            ("call another workflow to do the work", "manual_trigger"),
        ]

        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    LLMService._infer_parent_trigger_type_from_prompt(prompt),
                    expected,
                )

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

        self.assertIn("invalid if_else branch labels", str(context.exception))

    def test_validate_generated_workflow_accepts_ai_agent_with_chat_model_subnode(self) -> None:
        raw_content = json.dumps({"definition": _definition_for_prompt_kind("manual_ai_agent_openai")})

        definition, _ = LLMService.validate_generated_workflow(raw_content)

        actual_node_types = {node.type for node in definition.nodes}
        self.assertEqual(
            actual_node_types,
            {"manual_trigger", "ai_agent", "chat_model_openai"},
        )

    def test_validate_generated_workflow_rejects_ai_agent_without_chat_model_subnode(self) -> None:
        payload = _definition_for_prompt_kind("manual_ai_agent_openai")
        payload["edges"] = [payload["edges"][0]]

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertIn("must have exactly one connected", str(context.exception))

    def test_validate_generated_workflow_rejects_invalid_chat_model_target_handle(self) -> None:
        payload = _definition_for_prompt_kind("manual_ai_agent_openai")
        payload["edges"][1]["targetHandle"] = None

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertIn("targetHandle 'chat_model'", str(context.exception))

    def test_validate_generated_workflow_rejects_non_existent_edge_source_cleanly(self) -> None:
        payload = _valid_definition()
        payload["edges"][0]["source"] = "missing_node"

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertIn("edges with unknown nodes", str(context.exception))

    def test_validate_generated_workflow_rejects_non_existent_edge_target_cleanly(self) -> None:
        payload = _valid_definition()
        payload["edges"][0]["target"] = "missing_node"

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertIn("edges with unknown nodes", str(context.exception))

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

        result = await service.generate_workflow_definition(
            "Send a telegram message when I manually run the workflow"
        )

        self.assertEqual(result.definition.nodes[1].type, "telegram")
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
            (
                "When I manually run the workflow, use AI to draft a reply to the customer's message",
                "manual_ai_agent_openai",
                {"manual_trigger", "ai_agent", "chat_model_openai"},
            ),
            (
                "When I manually run the workflow, generate an image and post it to LinkedIn",
                "manual_image_linkedin",
                {"manual_trigger", "image_gen", "linkedin"},
            ),
        ]

        for prompt, definition_kind, expected_node_types in cases:
            fake_client = _FakeClient(
                responses=[json.dumps({"definition": _definition_for_prompt_kind(definition_kind)})]
            )
            service = LLMService(client=fake_client, model="test-model")

            result = await service.generate_workflow_definition(prompt)

            actual_node_types = {node.type for node in result.definition.nodes}
            self.assertTrue(
                expected_node_types.issubset(actual_node_types),
                msg=f"Prompt {prompt!r} produced node types {actual_node_types}, expected at least {expected_node_types}",
            )

    def test_validate_generated_workflow_accepts_image_gen_with_empty_credential(self) -> None:
        payload = _definition_for_prompt_kind("manual_image_linkedin")

        definition, _ = LLMService.validate_generated_workflow(
            json.dumps(payload),
            user_prompt="Generate an image and post it to LinkedIn",
        )

        image_node = next(node for node in definition.nodes if node.type == "image_gen")
        self.assertEqual(image_node.config["credential_id"], "")
        self.assertEqual(image_node.config["model"], "dall-e-3")
        self.assertIn("product launch image", image_node.config["prompt"])

    def test_validate_generated_workflow_requires_image_gen_when_prompt_requests_image(self) -> None:
        payload = _valid_definition()

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(
                json.dumps(payload),
                user_prompt="Generate an image and send it to Telegram",
            )

        self.assertIn("does not include an image_gen node", str(context.exception))

    def test_validate_generated_workflow_applies_schedule_hint_from_user_prompt(self) -> None:
        payload = _valid_definition()
        payload["nodes"][0]["type"] = "manual_trigger"
        payload["nodes"][0]["config"] = {}

        definition, _ = LLMService.validate_generated_workflow(
            json.dumps(payload),
            user_prompt="Run this every 15 minutes and send Telegram message",
        )

        self.assertEqual(definition.nodes[0].type, "schedule_trigger")
        self.assertEqual(definition.nodes[0].config["rules"][0]["interval"], "minutes")
        self.assertEqual(definition.nodes[0].config["rules"][0]["every"], 15)

    def test_validate_generated_workflow_infers_webhook_trigger_for_event_prompt(self) -> None:
        payload = _valid_definition()
        payload["nodes"][0]["type"] = "manual_trigger"
        payload["nodes"][0]["config"] = {}

        definition, _ = LLMService.validate_generated_workflow(
            json.dumps(payload),
            user_prompt="When a new order event arrives from Shopify API, send Telegram alert",
        )

        self.assertEqual(definition.nodes[0].type, "webhook_trigger")
        self.assertEqual(definition.nodes[0].config["method"], "POST")
        self.assertTrue(str(definition.nodes[0].config["path"]).strip())

    def test_validate_generated_workflow_infers_form_trigger_and_fields_for_lead_prompt(self) -> None:
        payload = _valid_definition()
        payload["nodes"][0]["type"] = "manual_trigger"
        payload["nodes"][0]["config"] = {}

        definition, _ = LLMService.validate_generated_workflow(
            json.dumps(payload),
            user_prompt="When a lead submits name, email and phone, send Telegram message",
        )

        self.assertEqual(definition.nodes[0].type, "form_trigger")
        fields = definition.nodes[0].config.get("fields") or []
        field_names = {
            str(item.get("name") or "").strip()
            for item in fields
            if isinstance(item, dict)
        }
        self.assertTrue({"name", "email", "phone"}.issubset(field_names))

    def test_generation_prompt_lists_expanded_form_field_types(self) -> None:
        system_prompt = LLMService.build_workflow_generation_system_prompt()

        self.assertIn("checkbox_group", system_prompt)
        self.assertIn("select, radio, and checkbox_group fields require options", system_prompt)
        self.assertIn("checkbox_group submits an array", system_prompt)

    def test_validate_generated_workflow_infers_checkbox_group_form_field(self) -> None:
        payload = _valid_definition()
        payload["nodes"][0]["type"] = "manual_trigger"
        payload["nodes"][0]["config"] = {}

        definition, _ = LLMService.validate_generated_workflow(
            json.dumps(payload),
            user_prompt="When a user submits affected platforms in a form, send Telegram message",
        )

        self.assertEqual(definition.nodes[0].type, "form_trigger")
        fields = definition.nodes[0].config.get("fields") or []
        affected_field = next(
            (
                item
                for item in fields
                if isinstance(item, dict)
                and str(item.get("name") or "").strip() == "affected_platforms"
            ),
            None,
        )
        self.assertIsNotNone(affected_field)
        self.assertEqual(affected_field["type"], "checkbox_group")
        self.assertGreaterEqual(len(affected_field.get("options") or []), 1)

    def test_validate_generated_workflow_prefers_groq_chat_model_when_prompt_mentions_groq(self) -> None:
        payload = _definition_for_prompt_kind("manual_ai_agent_openai")

        definition, _ = LLMService.validate_generated_workflow(
            json.dumps(payload),
            user_prompt="Use Groq model for this AI workflow",
        )

        node_types = {node.type for node in definition.nodes}
        self.assertIn("chat_model_groq", node_types)
        self.assertNotIn("chat_model_openai", node_types)

    def test_validate_generated_workflow_filters_unknown_config_keys(self) -> None:
        payload = _valid_definition()
        payload["nodes"][1]["config"]["unknown_extra_key"] = "drop_me"

        definition, _ = LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertNotIn("unknown_extra_key", definition.nodes[1].config)

    def test_validate_generated_workflow_normalizes_single_brace_templates(self) -> None:
        payload = _valid_definition()
        payload["nodes"][1]["config"]["message"] = "Hi {form.email}"

        definition, _ = LLMService.validate_generated_workflow(json.dumps(payload))

        self.assertEqual(definition.nodes[1].config["message"], "Hi {{form.email}}")

    def test_validate_generated_workflow_normalizes_ai_agent_structured_output_paths(self) -> None:
        payload = _definition_for_prompt_kind("manual_ai_agent_openai")
        payload["nodes"].append(
            {
                "id": "n4",
                "type": "telegram",
                "label": "Send Telegram Message",
                "position": {"x": 640, "y": 150},
                "config": {
                    "credential_id": "",
                    "message": (
                        "Summary {{n2.summary}} | "
                        "Sentiment {{$node[\"n2\"].json.sentiment}} | "
                        "Decision {{n2.output.decision}} | "
                        "Classification {{$node[\"n2\"].json.output.classification}} | "
                        "Ticket {{n2.ticket_id}} | "
                        "Local {{output.summary}}"
                    ),
                    "image": "",
                    "parse_mode": "",
                },
            }
        )
        payload["edges"].append(
            {
                "id": "e3",
                "source": "n2",
                "target": "n4",
                "sourceHandle": None,
                "targetHandle": None,
                "branch": None,
            }
        )

        definition, _ = LLMService.validate_generated_workflow(json.dumps(payload))
        telegram_node = next(node for node in definition.nodes if node.id == "n4")
        message = str(telegram_node.config.get("message") or "")

        self.assertIn("{{output.summary}}", message)
        self.assertIn("{{output.sentiment}}", message)
        self.assertIn("{{output.decision}}", message)
        self.assertIn("{{output.classification}}", message)
        self.assertIn("{{n2.ticket_id}}", message)
        self.assertNotIn("{{n2.summary}}", message)
        self.assertNotIn("{{$node[\"n2\"].json.sentiment}}", message)
        self.assertNotIn("{{n2.output.decision}}", message)
        self.assertNotIn("{{$node[\"n2\"].json.output.classification}}", message)

    def test_validate_generated_workflow_rejects_trigger_only_for_actionable_prompt(self) -> None:
        payload = {
            "nodes": [
                {
                    "id": "n1",
                    "type": "manual_trigger",
                    "label": "Manual Trigger",
                    "position": {"x": 100, "y": 120},
                    "config": {},
                }
            ],
            "edges": [],
        }

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(
                json.dumps(payload),
                user_prompt="Send a Telegram message when this workflow runs",
            )

        self.assertIn("trigger-only", str(context.exception))

    def test_validate_generated_workflow_allows_trigger_only_when_explicitly_requested(self) -> None:
        payload = {
            "nodes": [
                {
                    "id": "n1",
                    "type": "manual_trigger",
                    "label": "Manual Trigger",
                    "position": {"x": 100, "y": 120},
                    "config": {},
                }
            ],
            "edges": [],
        }

        definition, _ = LLMService.validate_generated_workflow(
            json.dumps(payload),
            user_prompt="Create a workflow with only manual trigger for now",
        )

        self.assertEqual(len(definition.nodes), 1)
        self.assertEqual(definition.nodes[0].type, "manual_trigger")

    def test_validate_generated_workflow_accepts_delay_days_unit(self) -> None:
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
                    "type": "delay",
                    "label": "Wait",
                    "position": {"x": 200, "y": 0},
                    "config": {"amount": "7", "unit": "days", "until_datetime": ""},
                },
                {
                    "id": "n3",
                    "type": "telegram",
                    "label": "Notify",
                    "position": {"x": 400, "y": 0},
                    "config": {"credential_id": "", "message": "Done", "parse_mode": ""},
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        definition, _ = LLMService.validate_generated_workflow(json.dumps(payload))

        delay_node = next(node for node in definition.nodes if node.type == "delay")
        self.assertEqual(delay_node.config["unit"], "days")
        self.assertEqual(delay_node.config["amount"], "7")

    def test_validate_generated_workflow_accepts_delay_months_unit(self) -> None:
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
                    "type": "delay",
                    "label": "Wait",
                    "position": {"x": 200, "y": 0},
                    "config": {"amount": "1", "unit": "months", "until_datetime": ""},
                },
                {
                    "id": "n3",
                    "type": "telegram",
                    "label": "Notify",
                    "position": {"x": 400, "y": 0},
                    "config": {"credential_id": "", "message": "Done", "parse_mode": ""},
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        definition, _ = LLMService.validate_generated_workflow(json.dumps(payload))

        delay_node = next(node for node in definition.nodes if node.type == "delay")
        self.assertEqual(delay_node.config["unit"], "months")

    def test_validate_generated_workflow_rejects_too_short_sequence_duration(self) -> None:
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
                    "type": "delay",
                    "label": "Wait",
                    "position": {"x": 200, "y": 0},
                    "config": {"amount": "1", "unit": "hours", "until_datetime": ""},
                },
                {
                    "id": "n3",
                    "type": "telegram",
                    "label": "Notify",
                    "position": {"x": 400, "y": 0},
                    "config": {"credential_id": "", "message": "Done", "parse_mode": ""},
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        }

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(
                json.dumps(payload),
                user_prompt="Build a 14-day sequence to nurture leads",
            )

        self.assertIn("Sequence duration does not match", str(context.exception))

    def test_validate_generated_workflow_rejects_linear_flow_when_prompt_requests_branching(self) -> None:
        payload = {
            "nodes": [
                {
                    "id": "n1",
                    "type": "form_trigger",
                    "label": "Lead Form",
                    "position": {"x": 0, "y": 0},
                    "config": {
                        "form_title": "Lead Form",
                        "form_description": "",
                        "fields": [{"name": "email", "label": "Email", "type": "email", "required": True}],
                    },
                },
                {
                    "id": "n2",
                    "type": "send_gmail_message",
                    "label": "Email",
                    "position": {"x": 200, "y": 0},
                    "config": {"credential_id": "", "to": "{{email}}", "cc": "", "bcc": "", "reply_to": "", "subject": "Hi", "body": "Hello", "is_html": False},
                },
                {
                    "id": "n3",
                    "type": "whatsapp",
                    "label": "WhatsApp",
                    "position": {"x": 400, "y": 0},
                    "config": {"credential_id": "", "to_number": "{{phone}}", "template_name": "hello_world", "template_params": [], "language_code": "en_US"},
                },
                {
                    "id": "n4",
                    "type": "telegram",
                    "label": "Telegram",
                    "position": {"x": 600, "y": 0},
                    "config": {"credential_id": "", "message": "Hello", "parse_mode": ""},
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n4"},
            ],
        }

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(
                json.dumps(payload),
                user_prompt="Create a 14-day lead nurture flow with email, WhatsApp, Telegram in parallel branches",
            )

        self.assertIn("does not fan out enough branches", str(context.exception))

    def test_validate_generated_workflow_rejects_overly_complex_simple_request(self) -> None:
        payload = {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "label": "Start", "position": {"x": 0, "y": 0}, "config": {}},
                {"id": "n2", "type": "filter", "label": "Filter 1", "position": {"x": 180, "y": 0}, "config": {"input_key": "", "field": "", "operator": "equals", "value": ""}},
                {"id": "n3", "type": "aggregate", "label": "Aggregate", "position": {"x": 360, "y": 0}, "config": {"input_key": "", "field": "", "operation": "count", "output_key": "count"}},
                {"id": "n4", "type": "delay", "label": "Delay", "position": {"x": 540, "y": 0}, "config": {"amount": "1", "unit": "minutes", "until_datetime": ""}},
                {"id": "n5", "type": "merge", "label": "Merge", "position": {"x": 720, "y": 0}, "config": {"mode": "append", "input_count": 2, "output_key": "merged"}},
                {"id": "n6", "type": "filter", "label": "Filter 2", "position": {"x": 900, "y": 0}, "config": {"input_key": "", "field": "", "operator": "equals", "value": ""}},
                {"id": "n7", "type": "telegram", "label": "Notify", "position": {"x": 1080, "y": 0}, "config": {"credential_id": "", "message": "hello", "parse_mode": ""}},
                {"id": "n8", "type": "create_google_docs", "label": "Doc", "position": {"x": 1260, "y": 0}, "config": {"credential_id": "", "title": "log", "initial_content": ""}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n4"},
                {"id": "e4", "source": "n4", "target": "n5"},
                {"id": "e5", "source": "n5", "target": "n6"},
                {"id": "e6", "source": "n6", "target": "n7"},
                {"id": "e7", "source": "n7", "target": "n8"},
            ],
        }

        with self.assertRaises(WorkflowGenerationError) as context:
            LLMService.validate_generated_workflow(
                json.dumps(payload),
                user_prompt="Send a Telegram message when I run the workflow manually",
            )

        self.assertIn("unnecessarily complex", str(context.exception))

    def test_validate_generated_workflow_accepts_trigger_fanout_for_multi_channel_prompt(self) -> None:
        payload = {
            "nodes": [
                {
                    "id": "n1",
                    "type": "form_trigger",
                    "label": "Lead Form",
                    "position": {"x": 0, "y": 0},
                    "config": {
                        "form_title": "Lead Form",
                        "form_description": "",
                        "fields": [{"name": "email", "label": "Email", "type": "email", "required": True}],
                    },
                },
                {
                    "id": "n2",
                    "type": "send_gmail_message",
                    "label": "Email",
                    "position": {"x": 200, "y": -80},
                    "config": {"credential_id": "", "to": "{{email}}", "cc": "", "bcc": "", "reply_to": "", "subject": "Hi", "body": "Hello", "is_html": False},
                },
                {
                    "id": "n3",
                    "type": "whatsapp",
                    "label": "WhatsApp",
                    "position": {"x": 200, "y": 0},
                    "config": {"credential_id": "", "to_number": "{{phone}}", "template_name": "hello_world", "template_params": [], "language_code": "en_US"},
                },
                {
                    "id": "n4",
                    "type": "telegram",
                    "label": "Telegram",
                    "position": {"x": 200, "y": 80},
                    "config": {"credential_id": "", "message": "Hello", "parse_mode": ""},
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n1", "target": "n3"},
                {"id": "e3", "source": "n1", "target": "n4"},
            ],
        }

        definition, _ = LLMService.validate_generated_workflow(
            json.dumps(payload),
            user_prompt="Create a 14-day lead nurture flow with email, WhatsApp, Telegram in parallel branches",
        )

        self.assertEqual(len(definition.edges), 3)

    async def test_assist_workflow_returns_clarify_for_low_confidence_prompt(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(prompt="help")

        self.assertEqual(result["mode"], "clarify")
        self.assertGreaterEqual(len(result["questions"]), 1)
        self.assertIsNone(result["definition"])

    async def test_assist_workflow_ask_mode_returns_guidance_without_definition(self) -> None:
        service = LLMService(client=object(), model="test-model")
        service._answer_autoflow_question = AsyncMock(  # type: ignore[attr-defined]
            return_value="Use webhook_trigger for API events and map values with {{payload.field}}."
        )
        service.generate_workflow_definition = AsyncMock()

        result = await service.assist_workflow(
            prompt="Which trigger is best for incoming API payloads?",
            interaction_mode="ask",
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIsNone(result["definition"])
        self.assertIn("webhook_trigger", result["assistant_message"])
        service._answer_autoflow_question.assert_awaited_once()
        service.generate_workflow_definition.assert_not_awaited()

    async def test_assist_workflow_ask_mode_uses_local_fallback_on_llm_error(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(_valid_definition())

        result = await service.assist_workflow(
            prompt="give the brief of this workflow and also provide upgrades",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIsNone(result["definition"])
        self.assertIn("Workflow Brief:", result["assistant_message"])
        self.assertIn("Suggested Upgrades:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_upgrades_include_ai_model_and_http_url_risks(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Webhook Trigger",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "inbound/support", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "ai_agent",
                        "label": "Classify",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            "system_prompt": "Analyze ticket",
                            "command": "Return summary",
                            "response_enhancement": "off",
                        },
                    },
                    {
                        "id": "n3",
                        "type": "http_request",
                        "label": "Sync API",
                        "position": {"x": 560, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "url": "",
                            "method": "POST",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="give brief and also provide upgrades for this workflow",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Suggested Upgrades:", result["assistant_message"])
        self.assertIn("Connect each ai_agent to one chat_model node", result["assistant_message"])
        self.assertIn("Set non-empty `url` for every http_request node", result["assistant_message"])

    async def test_assist_workflow_ask_mode_returns_routing_steps_and_parameters(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "form_trigger",
                        "label": "Form Trigger",
                        "position": {"x": 100, "y": 120},
                        "config": NODE_CONFIG_DEFAULTS["form_trigger"],
                    },
                    {
                        "id": "n2",
                        "type": "ai_agent",
                        "label": "Classify Input",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            "system_prompt": "Classify request",
                            "command": "Return summary and sentiment",
                            "response_enhancement": "off",
                        },
                    },
                    {
                        "id": "n3",
                        "type": "chat_model_openai",
                        "label": "OpenAI Chat Model",
                        "position": {"x": 340, "y": 320},
                        "config": NODE_CONFIG_DEFAULTS["chat_model_openai"],
                    },
                    {
                        "id": "n4",
                        "type": "image_gen",
                        "label": "Image Gen",
                        "position": {"x": 580, "y": 120},
                        "config": {
                            "credential_id": "",
                            "model": "dall-e-3",
                            "prompt": "Generate image for {{output.summary}}",
                            "size": "1024x1024",
                            "quality": "standard",
                            "style": "vivid",
                        },
                    },
                    {
                        "id": "n5",
                        "type": "linkedin",
                        "label": "LinkedIn",
                        "position": {"x": 820, "y": 120},
                        "config": {
                            "credential_id": "",
                            "post_text": "{{output.summary}}",
                            "image": "{{n4.image_url}}",
                            "visibility": "PUBLIC",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n3", "target": "n2", "targetHandle": "chat_model"},
                    {"id": "e3", "source": "n2", "target": "n4"},
                    {"id": "e4", "source": "n4", "target": "n5"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt=(
                "Add explicit routing logic (if_else/switch) so priority, sentiment, or category paths are handled clearly. "
                "what are steps to implement this and at which place this will come also give the parameters"
            ),
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIsNone(result["definition"])
        self.assertIn("Where to place it:", result["assistant_message"])
        self.assertIn("Implementation Steps:", result["assistant_message"])
        self.assertIn("if_else parameters", result["assistant_message"])
        self.assertIn("switch parameters", result["assistant_message"])
        self.assertIn("output.sentiment", result["assistant_message"])

    async def test_assist_workflow_ask_mode_routing_includes_existing_branch_map(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
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
                        "type": "if_else",
                        "label": "Priority Route",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["if_else"],
                            "field": "priority",
                            "operator": "equals",
                            "value": "urgent",
                        },
                    },
                    {
                        "id": "n3",
                        "type": "telegram",
                        "label": "Urgent Telegram",
                        "position": {"x": 580, "y": 80},
                        "config": NODE_CONFIG_DEFAULTS["telegram"],
                    },
                    {
                        "id": "n4",
                        "type": "send_gmail_message",
                        "label": "Normal Email",
                        "position": {"x": 580, "y": 180},
                        "config": NODE_CONFIG_DEFAULTS["send_gmail_message"],
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
                    {"id": "e3", "source": "n2", "target": "n4", "branch": "false"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="how to improve routing with if_else and where to place?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Branch map in your current workflow:", result["assistant_message"])
        self.assertIn("`n2` branch `true`", result["assistant_message"])
        self.assertIn("`n2` branch `false`", result["assistant_message"])
        self.assertIn("recommended: `priority`", result["assistant_message"])

    async def test_assist_workflow_ask_mode_answers_http_node_question_directly(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Receive Support Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "http_request",
                        "label": "Send To CRM API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                            "auth_mode": "bearer",
                            "body_type": "json",
                            "body_json": "{\"ticket_id\":\"{{ticket_id}}\",\"summary\":\"{{output.summary}}\"}",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="read flow and give idea what is this HTTP node and what i have to send and where i have to send",
            interaction_mode="ask",
            current_definition=current_definition,
            conversation_state={
                "recent_messages": [
                    {
                        "role": "assistant",
                        "content": "if_else parameters example: output.sentiment equals negative",
                    }
                ]
            },
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIsNone(result["definition"])
        self.assertIn("HTTP Node Overview:", result["assistant_message"])
        self.assertIn("https://api.example.com/tickets", result["assistant_message"])
        self.assertIn("What you have to send:", result["assistant_message"])
        self.assertIn("Where to send:", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("placement anchor:", result["assistant_message"])
        self.assertNotIn("if_else parameters", result["assistant_message"])

    async def test_assist_workflow_ask_mode_includes_context_pack_for_model_answer(self) -> None:
        fake_client = _FakeClient(responses=["Use this HTTP node to push ticket data to your CRM URL."])
        service = LLMService(client=fake_client, model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Receive Support Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "http_request",
                        "label": "Send To CRM API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                            "auth_mode": "bearer",
                            "body_type": "json",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="Explain Send To CRM API node and what payload I should send",
            interaction_mode="ask",
            current_definition=current_definition,
            conversation_state={
                "recent_messages": [
                    {"role": "user", "content": "We receive tickets by webhook"},
                    {"role": "assistant", "content": "Okay, we can map payload into crm request"},
                ]
            },
        )

        self.assertEqual(result["mode"], "ask")
        self.assertEqual(result["assistant_message"], "Use this HTTP node to push ticket data to your CRM URL.")
        self.assertGreater(len(fake_client.completions.calls), 0)
        user_prompt = str(fake_client.completions.calls[-1]["messages"][1]["content"])
        self.assertIn("Context pack:", user_prompt)
        self.assertIn("Focused node context:", user_prompt)
        self.assertIn("Send To CRM API (n2) type=http_request", user_prompt)
        self.assertIn("Recent chat memory:", user_prompt)

    async def test_assist_workflow_ask_mode_fallback_ladder_is_contextual(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(_valid_definition())

        result = await service.assist_workflow(
            prompt="help now",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Best-effort answer from available context:", result["assistant_message"])
        self.assertIn("What I still need to be exact:", result["assistant_message"])
        self.assertIn("Next action:", result["assistant_message"])
        self.assertNotIn("I can help in Ask mode with:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_handles_multi_node_questions(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Receive Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "http_request",
                        "label": "Sync CRM API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                            "body_type": "json",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="Explain webhook trigger and http request node with parameters",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("I found multiple node targets in your question:", result["assistant_message"])
        self.assertIn("Node: webhook_trigger", result["assistant_message"])
        self.assertIn("HTTP Node Overview:", result["assistant_message"])

    def test_resolve_node_focuses_from_prompt_uses_id_label_and_aliases(self) -> None:
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "support_webhook",
                        "type": "webhook_trigger",
                        "label": "Receive Support Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "merge_urgent_normal",
                        "type": "merge",
                        "label": "Join Urgent and Normal Save Path",
                        "position": {"x": 360, "y": 120},
                        "config": {"mode": "combine", "input_count": 2},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "support_webhook", "target": "merge_urgent_normal"},
                ],
            }
        )

        focuses = LLMService._resolve_node_focuses_from_prompt(
            "explain support_webhook and join urgent and normal save path with webhook details",
            current_definition=current_definition,
        )

        self.assertGreaterEqual(len(focuses), 2)
        self.assertEqual(focuses[0], "webhook_trigger")
        self.assertIn("merge", focuses)

    def test_build_ask_context_pack_contains_intent_and_multi_node_focuses(self) -> None:
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "webhook_in",
                        "type": "webhook_trigger",
                        "label": "Receive Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "http_sync",
                        "type": "http_request",
                        "label": "Sync Ticket API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                            "body_type": "json",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "webhook_in", "target": "http_sync"},
                ],
            }
        )

        pack = LLMService._build_ask_context_pack(
            question="How to configure webhook trigger and http request parameters?",
            current_definition=current_definition,
            recent_messages=[{"role": "user", "content": "we send ticket payload"}],
        )

        self.assertIn("inferred_intent=parameter_help", pack)
        self.assertIn("inferred_focus_node_types=", pack)
        self.assertIn("webhook_trigger", pack)
        self.assertIn("http_request", pack)

    def test_build_ask_context_pack_includes_context_origin_and_preview_state(self) -> None:
        current_definition = WorkflowDefinition.model_validate(_valid_definition())
        pack = LLMService._build_ask_context_pack(
            question="give brief",
            current_definition=current_definition,
            recent_messages=[],
            workflow_context_origin="accepted_canvas",
            preview_active=True,
            last_referenced_nodes=["merge_urgent_normal", "save_ticket_sheet"],
            last_unresolved_question="Should merge wait for both branches?",
            last_accepted_workflow_signature="sig-current-001",
        )

        self.assertIn("workflow_context_origin=accepted_canvas", pack)
        self.assertIn("preview_active=true", pack)
        self.assertIn("context_policy=prefer accepted canvas", pack)
        self.assertIn("memory_last_referenced_nodes=merge_urgent_normal, save_ticket_sheet", pack)
        self.assertIn("memory_last_unresolved_question=Should merge wait for both branches?", pack)
        self.assertIn("memory_last_accepted_workflow_signature=sig-current-001", pack)

    async def test_assist_workflow_ask_mode_quality_gate_rejects_generic_model_answer(self) -> None:
        fake_client = _FakeClient(
            responses=["I could not generate a useful answer yet. Please rephrase your question."]
        )
        service = LLMService(client=fake_client, model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Receive Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "http_request",
                        "label": "Sync Ticket API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                            "body_type": "json",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            }
        )

        result = await service.assist_workflow(
            prompt="explain http request node",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("HTTP Node Overview:", result["assistant_message"])
        self.assertNotIn("Please rephrase your question", result["assistant_message"])

    def test_ask_quality_checklist_flags_generic_answer(self) -> None:
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Receive Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "http_request",
                        "label": "Sync Ticket API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                            "body_type": "json",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            }
        )

        checklist = LLMService._evaluate_ask_quality_checklist(
            answer="you can choose best practices based on your goal",
            question="explain http request node and payload",
            current_definition=current_definition,
        )

        self.assertFalse(checklist["specificity"])
        self.assertFalse(checklist["actionability"])
        self.assertFalse(checklist["correctness"])

    def test_is_low_quality_ask_response_uses_checklist_gate(self) -> None:
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Receive Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "http_request",
                        "label": "Sync Ticket API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                            "body_type": "json",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            }
        )

        is_low_quality = LLMService._is_low_quality_ask_response(
            answer="consider good practices and choose the right setup",
            question="explain http request node and payload",
            current_definition=current_definition,
        )

        self.assertTrue(is_low_quality)

    async def test_assist_workflow_ask_mode_brief_prefers_accepted_canvas_context(self) -> None:
        service = LLMService(client=object(), model="test-model")
        accepted_definition = WorkflowDefinition.model_validate(_valid_definition())

        result = await service.assist_workflow(
            prompt="give the brief of this workflow",
            interaction_mode="ask",
            current_definition=accepted_definition,
            conversation_state={
                "workflow_context_origin": "accepted_canvas",
                "preview_active": True,
                "recent_messages": [
                    {"role": "assistant", "content": "Preview draft has 5 nodes and 6 edges"}
                ],
            },
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Workflow Brief:", result["assistant_message"])
        self.assertIn("This workflow has 2 nodes and 1 edges.", result["assistant_message"])
        self.assertNotIn("5 nodes", result["assistant_message"])

    async def test_assist_workflow_ask_mode_brief_includes_flow_shape_metadata(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Webhook Trigger",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "inbound/support", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "if_else",
                        "label": "Route Priority",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["if_else"],
                            "field": "priority",
                            "value": "urgent",
                        },
                    },
                    {
                        "id": "n3",
                        "type": "telegram",
                        "label": "Notify Telegram",
                        "position": {"x": 580, "y": 80},
                        "config": NODE_CONFIG_DEFAULTS["telegram"],
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="give brief of this workflow",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Workflow Brief:", result["assistant_message"])
        self.assertIn("Flow shape: branched.", result["assistant_message"])
        self.assertIn("Trigger node id: `n1`.", result["assistant_message"])

    async def test_assist_workflow_ask_mode_passes_memory_anchors_into_model_prompt(self) -> None:
        fake_client = _FakeClient(
            responses=[
                (
                    "Direct answer: use http_request with method POST and body_json. "
                    "In your current workflow n2 handles API sync. "
                    "Where to place it: after webhook trigger."
                )
            ]
        )
        service = LLMService(client=fake_client, model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Receive Support Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "http_request",
                        "label": "Send To CRM API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                            "auth_mode": "bearer",
                            "body_type": "json",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            }
        )

        result = await service.assist_workflow(
            prompt="Explain Send To CRM API node and payload",
            interaction_mode="ask",
            current_definition=current_definition,
            conversation_state={
                "last_referenced_nodes": ["n2", "n1"],
                "last_unresolved_question": "Should we retry before routing?",
                "last_accepted_workflow_signature": "sig-accepted-999",
                "recent_messages": [
                    {"role": "user", "content": "We sync from webhook to crm"},
                ],
            },
        )

        self.assertEqual(result["mode"], "ask")
        user_prompt = str(fake_client.completions.calls[-1]["messages"][1]["content"])
        self.assertIn("memory_last_referenced_nodes=n2, n1", user_prompt)
        self.assertIn("memory_last_unresolved_question=Should we retry before routing?", user_prompt)
        self.assertIn("memory_last_accepted_workflow_signature=sig-accepted-999", user_prompt)

    async def test_assist_workflow_ask_mode_answers_merge_node_question(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "merge_urgent_normal",
                        "type": "merge",
                        "label": "Join Urgent and Normal Save Path",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["merge"],
                            "mode": "combine",
                            "input_count": 2,
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "merge_urgent_normal"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="what this Join Urgent and Normal Save Path node do and what parameters should i use",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIsNone(result["definition"])
        self.assertIn("Node: merge", result["assistant_message"])
        self.assertIn("Key parameters:", result["assistant_message"])
        self.assertIn("mode", result["assistant_message"])
        self.assertIn("input_count", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("Concrete parameter example from schema:", result["assistant_message"])
        self.assertIn("placement anchor:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_explains_sort_node_directly(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt="what does sort node do?",
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Node: sort", result["assistant_message"])
        self.assertIn("Key parameters:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_unknown_node_returns_supported_alternatives(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt="what does read_google_doc node do?",
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("is not recognized as an Autoflow node type", result["assistant_message"])
        self.assertIn("Closest supported nodes:", result["assistant_message"])
        self.assertIn("read_google_docs", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_shows_required_params_for_read_google_docs(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt="What parameters are required in read_google_docs?",
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Node: read_google_docs", result["assistant_message"])
        self.assertIn("Required parameters:", result["assistant_message"])
        self.assertIn("credential_id", result["assistant_message"])
        self.assertIn("document_id OR document_url", result["assistant_message"])

    async def test_assist_workflow_ask_mode_placement_guidance_for_limit_node(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Incoming Webhook",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "lead/inbound", "method": "POST"},
                    },
                    {
                        "id": "n2",
                        "type": "code",
                        "label": "Prepare Array",
                        "position": {"x": 340, "y": 120},
                        "config": NODE_CONFIG_DEFAULTS["code"],
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            }
        )

        result = await service.assist_workflow(
            prompt="Where should I place limit node in this flow?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Node: limit", result["assistant_message"])
        self.assertIn("Where to place/use it:", result["assistant_message"])
        self.assertIn("outputs your target array", result["assistant_message"])

    async def test_assist_workflow_ask_mode_multi_node_has_combined_placement_guide(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt="Explain limit + sort + filter together for my workflow",
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Combined placement guide:", result["assistant_message"])
        self.assertIn("Recommended chain:", result["assistant_message"])
        self.assertIn("filter", result["assistant_message"])
        self.assertIn("sort", result["assistant_message"])
        self.assertIn("limit", result["assistant_message"])

    async def test_assist_workflow_ask_mode_returns_sequence_for_build_steps_request(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt=(
                "i want to create one workflow so basiaclly that workflow is trigger everyday in morning "
                "and featch the news from the website newsapi and filter the news which are related to the "
                "AI, ML, Tech and space related fetch top 10 news and then give that to the AI agent for "
                "creating summary and now summarize all news are share to the telegram so what wil be a steps "
                "and which nodes are conncect in sequence"
            ),
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Implementation Steps:", result["assistant_message"])
        self.assertIn("Nodes in sequence:", result["assistant_message"])
        self.assertIn("schedule_trigger", result["assistant_message"])
        self.assertIn("http_request", result["assistant_message"])
        self.assertIn("ai_agent", result["assistant_message"])
        self.assertIn("telegram", result["assistant_message"])
        self.assertIn("Why this order:", result["assistant_message"])
        self.assertNotIn("whatsapp", result["assistant_message"])
        self.assertNotIn("I found multiple node targets", result["assistant_message"])

    async def test_assist_workflow_ask_mode_returns_blueprint_for_multichannel_nurture_prompt(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt=(
                "create a nuturing workflow for 14 days lead geneartion from different apps "
                "like watsapp , telegram , slack , gmail , likendin for this workflow which "
                "nodes required and give the logical conncection"
            ),
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Implementation Steps:", result["assistant_message"])
        self.assertIn("Nodes in sequence:", result["assistant_message"])
        self.assertIn("schedule_trigger", result["assistant_message"])
        self.assertIn("telegram", result["assistant_message"])
        self.assertIn("whatsapp", result["assistant_message"])
        self.assertIn("slack_send_message", result["assistant_message"])
        self.assertIn("send_gmail_message", result["assistant_message"])
        self.assertIn("linkedin", result["assistant_message"])
        self.assertNotIn("I found multiple node targets", result["assistant_message"])

    async def test_assist_workflow_ask_mode_debugs_http_404_with_direct_fix_steps(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "schedule_trigger",
                        "label": "Morning Schedule",
                        "position": {"x": 100, "y": 120},
                        "config": NODE_CONFIG_DEFAULTS["schedule_trigger"],
                    },
                    {
                        "id": "sync_api",
                        "type": "http_request",
                        "label": "Sync Ticket API",
                        "position": {"x": 360, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://www.google.com/non-existent-endpoint",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "sync_api"}],
            }
        )

        result = await service.assist_workflow(
            prompt=(
                "HTTP request failed: 404 Not Found. in http node what error is come and how i can solve"
            ),
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("HTTP 404 Not Found", result["assistant_message"])
        self.assertIn("Likely root causes:", result["assistant_message"])
        self.assertIn("Likely failing node(s):", result["assistant_message"])
        self.assertIn("Fast triage order:", result["assistant_message"])
        self.assertIn("Fix steps:", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_debugs_merge_waiting_state(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "route",
                        "type": "if_else",
                        "label": "Urgent?",
                        "position": {"x": 300, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["if_else"],
                            "field": "priority",
                            "value": "urgent",
                        },
                    },
                    {
                        "id": "merge_wait",
                        "type": "merge",
                        "label": "Join Urgent and Normal Save Path",
                        "position": {"x": 520, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["merge"],
                            "mode": "append",
                            "input_count": 2,
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "route"},
                    {"id": "e2", "source": "route", "target": "merge_wait", "branch": "true", "targetHandle": "input1"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="merge node is waiting and stuck, why runtime error come?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("merge node is waiting", result["assistant_message"].lower())
        self.assertIn("input_count", result["assistant_message"])
        self.assertIn("Fix steps:", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_handles_credential_oauth_troubleshooting_explicitly(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "save_ticket_sheet",
                        "type": "search_update_google_sheets",
                        "label": "Save Ticket Sheet",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["search_update_google_sheets"],
                            "credential_id": "cred_google_sheets_1",
                            "spreadsheet_source_type": "id",
                            "spreadsheet_id": "sheet_123",
                            "sheet_name": "Tickets",
                            "operation": "append_row",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "save_ticket_sheet"}],
            }
        )

        result = await service.assist_workflow(
            prompt="Why my Google Sheets credential shows connected but node fails 403?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("credential/oauth troubleshooting case", result["assistant_message"].lower())
        self.assertIn("Detected status code: 403.", result["assistant_message"])
        self.assertIn("Credential checks to run first:", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("Save Ticket Sheet (save_ticket_sheet)", result["assistant_message"])
        self.assertIn("fix focus:", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    def test_classify_ask_intent_detects_credential_oauth(self) -> None:
        intent = LLMService._classify_ask_intent(
            "Google Sheets credential is connected but workflow fails with 403 forbidden. How to fix OAuth?"
        )
        self.assertEqual(intent, "credential_oauth")

    def test_classify_ask_intent_detects_trigger_configuration(self) -> None:
        intent = LLMService._classify_ask_intent(
            "Give me exact cron for weekdays 9:30 AM IST and configure schedule trigger."
        )
        self.assertEqual(intent, "trigger_config")

    def test_classify_ask_intent_detects_mapping_validation(self) -> None:
        intent = LLMService._classify_ask_intent(
            "Check if these template fields exist from previous node output: {{output.summary}}, {{output.decision}}"
        )
        self.assertEqual(intent, "mapping_validate")

    def test_classify_ask_intent_detects_schema_contract(self) -> None:
        intent = LLMService._classify_ask_intent(
            "What JSON schema should http_request body follow for this API?"
        )
        self.assertEqual(intent, "schema_contract")

    def test_classify_ask_intent_detects_merge_strategy(self) -> None:
        intent = LLMService._classify_ask_intent(
            "Should I use append or combine_by_fields in this merge case?"
        )
        self.assertEqual(intent, "merge_strategy")

    def test_classify_ask_intent_detects_loop_control(self) -> None:
        intent = LLMService._classify_ask_intent(
            "How to stop this split/merge loop from running forever?"
        )
        self.assertEqual(intent, "loop_control")

    def test_classify_ask_intent_detects_execution_log_debug(self) -> None:
        intent = LLMService._classify_ask_intent(
            "Analyze execution run id 8f2ab91 and node id sync_ticket_http, tell exact failing edge and fix"
        )
        self.assertEqual(intent, "execution_log_debug")

    def test_classify_ask_intent_detects_reliability_patterns(self) -> None:
        intent = LLMService._classify_ask_intent(
            "How do I add safe retry + fallback + idempotency for WhatsApp delivery failures?"
        )
        self.assertEqual(intent, "reliability_patterns")

    def test_classify_ask_intent_detects_performance_scaling(self) -> None:
        intent = LLMService._classify_ask_intent(
            "How to reduce runtime and API calls for this 12-node workflow?"
        )
        self.assertEqual(intent, "performance_scaling")

    def test_classify_ask_intent_detects_security_pii(self) -> None:
        intent = LLMService._classify_ask_intent(
            "Where can this workflow leak secrets and PII, and how to secure it?"
        )
        self.assertEqual(intent, "security_pii")

    def test_classify_ask_intent_detects_publish_ops(self) -> None:
        intent = LLMService._classify_ask_intent(
            "Checklist before publishing this workflow to production?"
        )
        self.assertEqual(intent, "publish_ops")

    def test_classify_ask_intent_detects_n8n_migration(self) -> None:
        intent = LLMService._classify_ask_intent(
            "This imported n8n flow failed; what config translation is missing?"
        )
        self.assertEqual(intent, "n8n_migration")

    async def test_assist_workflow_ask_mode_capabilities_response_covers_full_scope(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt="what can ask mode do for all nodes and workflows?",
            interaction_mode="ask",
            current_definition=WorkflowDefinition.model_validate(_valid_definition()),
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Ask mode capabilities:", result["assistant_message"])
        self.assertIn("create", result["assistant_message"].lower())
        self.assertIn("edit", result["assistant_message"].lower())
        self.assertIn("runtime debugging", result["assistant_message"].lower())
        self.assertIn("Current limits:", result["assistant_message"])
        self.assertIn("Supported ask examples:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_prompt_improvement_returns_ai_prompt_rewrite(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Manual",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "summarize_issue_ai",
                        "type": "ai_agent",
                        "label": "Summarize Issue",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            "system_prompt": "You are support triage helper.",
                            "command": "Analyze ticket and return JSON with keys: summary, sentiment, recommended_action",
                            "response_enhancement": "off",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "summarize_issue_ai"}],
            }
        )

        result = await service.assist_workflow(
            prompt="read the system prompt and if prompt is not good suggest better prompt",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Suggested replacement for `summarize_issue_ai`:", result["assistant_message"])
        self.assertIn("system_prompt:", result["assistant_message"])
        self.assertIn("command:", result["assistant_message"])
        self.assertIn("Downstream template mapping:", result["assistant_message"])
        self.assertIn("{{output.summary}}", result["assistant_message"])

    async def test_assist_workflow_ask_mode_general_best_trigger_question_returns_direct_recommendation(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt="Best trigger for incoming API payloads?",
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Recommended trigger: `webhook_trigger`", result["assistant_message"])
        self.assertIn("Quick selection guide:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_trigger_configuration_returns_exact_weekday_cron(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt="Give me exact cron for weekdays 9:30 AM IST.",
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Trigger configuration assistant", result["assistant_message"])
        self.assertIn("`schedule_trigger`", result["assistant_message"])
        self.assertIn("Exact cron:", result["assistant_message"])
        self.assertIn("30 9 * * 1-5", result["assistant_message"])
        self.assertIn("Asia/Kolkata", result["assistant_message"])
        self.assertIn("Implementation steps:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_trigger_configuration_webhook_returns_path_and_method(self) -> None:
        service = LLMService(client=object(), model="test-model")

        result = await service.assist_workflow(
            prompt="Configure webhook trigger for POST /customer-support/request",
            interaction_mode="ask",
            current_definition=None,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("`webhook_trigger`", result["assistant_message"])
        self.assertIn("Exact webhook config:", result["assistant_message"])
        self.assertIn("customer-support/request", result["assistant_message"])
        self.assertIn("POST", result["assistant_message"])
        self.assertIn("Parameters:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_mapping_validation_reports_valid_and_risk(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "support_webhook",
                        "type": "webhook_trigger",
                        "label": "Receive Support Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "summarize_issue_ai",
                        "type": "ai_agent",
                        "label": "Summarize Ticket",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            "system_prompt": "You are support triage assistant. Return strict JSON only.",
                            "command": "Analyze ticket and return JSON with keys: summary, sentiment, recommended_action",
                            "response_enhancement": "off",
                        },
                    },
                    {
                        "id": "telegram_alert",
                        "type": "telegram",
                        "label": "Send Alert",
                        "position": {"x": 580, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["telegram"],
                            "message": "Summary: {{output.summary}} | Decision: {{output.decision}} | Ticket: {{ticket_id}}",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "support_webhook", "target": "summarize_issue_ai"},
                    {"id": "e2", "source": "summarize_issue_ai", "target": "telegram_alert"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt=(
                "Check if these template fields exist from previous node output for telegram_alert: "
                "{{output.summary}}, {{output.decision}}, {{ticket_id}}"
            ),
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Mapping validation report:", result["assistant_message"])
        self.assertIn("Send Alert (telegram_alert)", result["assistant_message"])
        self.assertIn("{{output.summary}}", result["assistant_message"])
        self.assertIn("VALID", result["assistant_message"])
        self.assertIn("{{output.decision}}", result["assistant_message"])
        self.assertIn("RISK", result["assistant_message"])
        self.assertIn("Summary:", result["assistant_message"])
        self.assertIn("checked=", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_schema_contract_for_http_request_body(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "webhook_trigger",
                        "label": "Receive Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "sync_ticket_http",
                        "type": "http_request",
                        "label": "Sync Ticket API",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "url": "https://api.example.com/tickets",
                            "method": "POST",
                            "body_type": "json",
                            "body_json": "{\"ticket_id\":\"{{ticket_id}}\",\"summary\":\"{{output.summary}}\"}",
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "sync_ticket_http"}],
            }
        )

        result = await service.assist_workflow(
            prompt="What JSON schema should http_request body follow for this API?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Schema contract guidance:", result["assistant_message"])
        self.assertIn("Node: `http_request`", result["assistant_message"])
        self.assertIn("JSON schema starter for `body_json`:", result["assistant_message"])
        self.assertIn("request body example:", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("Sync Ticket API (sync_ticket_http)", result["assistant_message"])
        self.assertIn("Validation steps:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_merge_strategy_advises_mode_selection(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "route_priority",
                        "type": "if_else",
                        "label": "Is Priority Urgent?",
                        "position": {"x": 320, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["if_else"],
                            "field": "priority",
                            "value": "urgent",
                        },
                    },
                    {
                        "id": "merge_paths",
                        "type": "merge",
                        "label": "Join Urgent and Normal Save Path",
                        "position": {"x": 560, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["merge"],
                            "mode": "append",
                            "input_count": 2,
                            "output_key": "merged",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "route_priority"},
                    {"id": "e2", "source": "route_priority", "target": "merge_paths", "branch": "true", "targetHandle": "input1"},
                    {"id": "e3", "source": "route_priority", "target": "merge_paths", "branch": "false", "targetHandle": "input2"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="Should I use append or combine_by_fields in this merge case for same ticket_id?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Recommended merge mode: `combine_by_fields`", result["assistant_message"])
        self.assertIn("Mode chooser:", result["assistant_message"])
        self.assertIn("Append vs combine_by_fields decision:", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("Join Urgent and Normal Save Path (merge_paths)", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_loop_control_prevention_guidance(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "split_items",
                        "type": "split_in",
                        "label": "Split Items",
                        "position": {"x": 320, "y": 120},
                        "config": NODE_CONFIG_DEFAULTS["split_in"],
                    },
                    {
                        "id": "check_exit",
                        "type": "if_else",
                        "label": "Continue Loop?",
                        "position": {"x": 560, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["if_else"],
                            "field": "continue_loop",
                            "value": "true",
                        },
                    },
                    {
                        "id": "collect_results",
                        "type": "split_out",
                        "label": "Collect Results",
                        "position": {"x": 800, "y": 120},
                        "config": NODE_CONFIG_DEFAULTS["split_out"],
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "split_items"},
                    {"id": "e2", "source": "split_items", "target": "check_exit"},
                    {"id": "e3", "source": "check_exit", "target": "split_items", "branch": "true", "targetHandle": "input1"},
                    {"id": "e4", "source": "check_exit", "target": "collect_results", "branch": "false"},
                ],
                "loop_control": {
                    "enabled": True,
                    "max_node_executions": 20,
                    "max_total_node_executions": 5000,
                },
            }
        )

        result = await service.assist_workflow(
            prompt="How to stop this split/merge loop from running forever?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Loop prevention strategy:", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("loop_control:", result["assistant_message"])
        self.assertIn("Detected cycle candidates:", result["assistant_message"])
        self.assertIn("Suggested loop_control baseline:", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_execution_log_debug_reports_edge_candidates(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "start",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "sync_ticket_http",
                        "type": "http_request",
                        "label": "Sync Ticket API",
                        "position": {"x": 320, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/v1/tickets",
                        },
                    },
                    {
                        "id": "priority_check",
                        "type": "if_else",
                        "label": "Priority Check",
                        "position": {"x": 560, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["if_else"],
                            "field": "priority",
                            "value": "urgent",
                        },
                    },
                    {
                        "id": "notify_telegram",
                        "type": "telegram",
                        "label": "Send Telegram Alert",
                        "position": {"x": 800, "y": 80},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["telegram"],
                            "message": "Ticket {{ticket_id}}",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "sync_ticket_http"},
                    {"id": "e2", "source": "sync_ticket_http", "target": "priority_check"},
                    {
                        "id": "e3",
                        "source": "priority_check",
                        "target": "notify_telegram",
                        "branch": "true",
                        "sourceHandle": "true",
                    },
                ],
            }
        )

        result = await service.assist_workflow(
            prompt=(
                "Analyze execution run id 8f2ab91 and node id sync_ticket_http. "
                "HTTP request failed: 404 Not Found. Tell exact failing edge and fix."
            ),
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Execution log context:", result["assistant_message"])
        self.assertIn("Run id: `8f2ab91`", result["assistant_message"])
        self.assertIn("sync_ticket_http", result["assistant_message"])
        self.assertIn("Exact failing-edge candidates:", result["assistant_message"])
        self.assertIn("Start (start) -> Sync Ticket API (sync_ticket_http)", result["assistant_message"])
        self.assertIn("Edge-focused fix steps:", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_reliability_patterns_returns_retry_fallback_idempotency_plan(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "support_webhook",
                        "type": "webhook_trigger",
                        "label": "Receive Support Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "sync_ticket_http",
                        "type": "http_request",
                        "label": "Sync Ticket API",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "POST",
                            "url": "https://api.example.com/tickets",
                        },
                    },
                    {
                        "id": "whatsapp_alert",
                        "type": "whatsapp",
                        "label": "Send WhatsApp Alert",
                        "position": {"x": 580, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["whatsapp"],
                            "template_name": "urgent_support_alert",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "support_webhook", "target": "sync_ticket_http"},
                    {"id": "e2", "source": "sync_ticket_http", "target": "whatsapp_alert"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="How do I add safe retry + fallback for WhatsApp failure and prevent duplicate sends with idempotency?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Reliability design pattern:", result["assistant_message"])
        self.assertIn("retry", result["assistant_message"].lower())
        self.assertIn("backoff", result["assistant_message"].lower())
        self.assertIn("fallback", result["assistant_message"].lower())
        self.assertIn("idempotency", result["assistant_message"].lower())
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("Send WhatsApp Alert (whatsapp_alert)", result["assistant_message"])
        self.assertIn("Recommended config snippets:", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_performance_scaling_returns_optimization_plan(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "daily_trigger",
                        "type": "schedule_trigger",
                        "label": "Daily Trigger",
                        "position": {"x": 100, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["schedule_trigger"],
                            "timezone": "Asia/Kolkata",
                        },
                    },
                    {
                        "id": "fetch_news",
                        "type": "http_request",
                        "label": "Fetch News API",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "GET",
                            "url": "https://newsapi.org/v2/everything?q=ai&pageSize=100",
                        },
                    },
                    {
                        "id": "summarize_news",
                        "type": "ai_agent",
                        "label": "Summarize News",
                        "position": {"x": 580, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["ai_agent"],
                            "command": "Summarize all fetched news",
                        },
                    },
                    {
                        "id": "post_linkedin",
                        "type": "linkedin",
                        "label": "Post to LinkedIn",
                        "position": {"x": 820, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["linkedin"],
                            "post_text": "{{output.summary}}",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "daily_trigger", "target": "fetch_news"},
                    {"id": "e2", "source": "fetch_news", "target": "summarize_news"},
                    {"id": "e3", "source": "summarize_news", "target": "post_linkedin"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="How to reduce runtime and API calls for this workflow and scale better?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Performance and scaling plan:", result["assistant_message"])
        self.assertIn("api calls", result["assistant_message"].lower())
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("Fetch News API (fetch_news)", result["assistant_message"])
        self.assertIn("Recommended tuning snippets:", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_security_pii_returns_hardening_checklist(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "support_webhook",
                        "type": "webhook_trigger",
                        "label": "Receive Support Request",
                        "position": {"x": 100, "y": 120},
                        "config": {"path": "support/inbound", "method": "POST"},
                    },
                    {
                        "id": "sync_http",
                        "type": "http_request",
                        "label": "Sync CRM API",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "url": "https://api.example.com/v1/tickets",
                            "method": "POST",
                            "bearer_token": "secret-token-value",
                            "body_json": "{\"email\":\"{{customer.email}}\",\"phone\":\"{{customer.phone}}\"}",
                        },
                    },
                    {
                        "id": "send_email",
                        "type": "send_gmail_message",
                        "label": "Send Confirmation",
                        "position": {"x": 580, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["send_gmail_message"],
                            "to": "{{customer.email}}",
                            "subject": "Ticket {{ticket_id}}",
                            "body": "Hi {{customer.name}}, we got your request.",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "support_webhook", "target": "sync_http"},
                    {"id": "e2", "source": "sync_http", "target": "send_email"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="Where can this workflow leak secrets and PII, and how to secure it?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Security & PII hardening checklist:", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("possible pii", result["assistant_message"].lower())
        self.assertIn("Send Confirmation (send_email)", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_publish_ops_returns_go_live_checklist(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "daily_trigger",
                        "type": "schedule_trigger",
                        "label": "Daily Trigger",
                        "position": {"x": 100, "y": 120},
                        "config": NODE_CONFIG_DEFAULTS["schedule_trigger"],
                    },
                    {
                        "id": "fetch_news",
                        "type": "http_request",
                        "label": "Fetch News API",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["http_request"],
                            "method": "GET",
                            "url": "https://newsapi.org/v2/everything?q=ai",
                        },
                    },
                    {
                        "id": "post_telegram",
                        "type": "telegram",
                        "label": "Post Telegram Update",
                        "position": {"x": 580, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["telegram"],
                            "message": "Daily update {{summary}}",
                            "credential_id": "",
                        },
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "daily_trigger", "target": "fetch_news"},
                    {"id": "e2", "source": "fetch_news", "target": "post_telegram"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="Checklist before publishing this workflow to production?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Publish/deploy operations checklist:", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("go-live readiness", result["assistant_message"].lower())
        self.assertIn("Immediate blockers:", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_n8n_migration_returns_compatibility_guidance(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "n8n_http",
                        "type": "n8n-nodes-base.httpRequest",
                        "label": "HTTP Request",
                        "position": {"x": 340, "y": 120},
                        "config": {
                            "url": "https://api.example.com/v1/tickets",
                            "method": "POST",
                        },
                    },
                    {
                        "id": "n8n_set",
                        "type": "n8n-nodes-base.set",
                        "label": "Set Fields",
                        "position": {"x": 580, "y": 120},
                        "config": {
                            "values": {"string": [{"name": "ticket_id", "value": "={{$json.id}}"}]}
                        },
                    },
                    {
                        "id": "n8n_unknown",
                        "type": "n8n-nodes-base.splitInBatches",
                        "label": "Split In Batches",
                        "position": {"x": 820, "y": 120},
                        "config": {"batchSize": 10},
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n8n_http"},
                    {"id": "e2", "source": "n8n_http", "target": "n8n_set"},
                    {"id": "e3", "source": "n8n_set", "target": "n8n_unknown"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="This imported n8n flow failed; what config translation is missing?",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("n8n compatibility/migration advisor:", result["assistant_message"])
        self.assertIn("In your current workflow:", result["assistant_message"])
        self.assertIn("n8n-nodes-base.httpRequest", result["assistant_message"])
        self.assertIn("Immediate compatibility risks:", result["assistant_message"])
        self.assertIn("splitInBatches", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    async def test_assist_workflow_ask_mode_email_format_includes_html_and_validation_checklist(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "n2",
                        "type": "send_gmail_message",
                        "label": "Send Email",
                        "position": {"x": 320, "y": 120},
                        "config": {
                            **NODE_CONFIG_DEFAULTS["send_gmail_message"],
                            "to": "{{email}}",
                            "subject": "Support update",
                            "body": "Hi {{name}}",
                            "is_html": False,
                        },
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
            }
        )

        result = await service.assist_workflow(
            prompt="Improve mail format in this workflow",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Template (HTML, when `is_html=true`):", result["assistant_message"])
        self.assertIn("Validation checklist:", result["assistant_message"])
        self.assertIn("include `{{ticket_id}}` in subject", result["assistant_message"])

    async def test_assist_workflow_ask_mode_treats_fail_problem_phrase_as_debug(self) -> None:
        service = LLMService(client=object(), model="test-model")
        current_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "manual_trigger",
                        "label": "Start",
                        "position": {"x": 100, "y": 120},
                        "config": {},
                    },
                    {
                        "id": "n2",
                        "type": "file_read",
                        "label": "Read Input",
                        "position": {"x": 320, "y": 120},
                        "config": NODE_CONFIG_DEFAULTS["file_read"],
                    },
                    {
                        "id": "n3",
                        "type": "ai_agent",
                        "label": "Analyze",
                        "position": {"x": 540, "y": 120},
                        "config": NODE_CONFIG_DEFAULTS["ai_agent"],
                    },
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3"},
                ],
            }
        )

        result = await service.assist_workflow(
            prompt="which problem is there which was fail the workflow so give solution for that problem",
            interaction_mode="ask",
            current_definition=current_definition,
        )

        self.assertEqual(result["mode"], "ask")
        self.assertIn("Likely root causes:", result["assistant_message"])
        self.assertIn("Fix steps:", result["assistant_message"])
        self.assertNotIn("Workflow Brief:", result["assistant_message"])

    def test_extract_latest_user_question_skips_pasted_brief_blocks(self) -> None:
        raw = (
            "give some improvement for sending message to the mail for formate related what changes i can do\n"
            "Copy\n"
            "12:55 PM\n"
            "Workflow Brief:\n"
            "- This workflow has 5 nodes and 4 edges.\n"
            "Copy\n"
            "12:56 PM\n"
            "Assumptions Applied\n"
            "1. Single-path flow is used when branch conditions are not provided.\n"
            "read the system prompt and if the prompt is not good then sudgest good promts"
        )

        extracted = LLMService._extract_latest_user_question(raw)

        self.assertIn("read the system prompt", extracted.lower())
        self.assertNotIn("workflow brief", extracted.lower())

    def test_extract_latest_user_question_preserves_recent_error_context(self) -> None:
        raw = (
            "HTTP request failed: 404 Not Found - https://api.example.com/v1/tickets\n"
            "in http node what error is come and how i can solve"
        )

        extracted = LLMService._extract_latest_user_question(raw)

        self.assertIn("how i can solve", extracted.lower())
        self.assertIn("error context:", extracted.lower())
        self.assertIn("404", extracted)

    async def test_assist_workflow_generates_directly_for_clear_request(self) -> None:
        fake_client = _FakeClient(
            responses=[json.dumps({"definition": _valid_definition()})]
        )
        service = LLMService(client=fake_client, model="test-model")

        result = await service.assist_workflow(
            prompt="Send a telegram message when I run the workflow manually",
        )

        self.assertEqual(result["mode"], "generate")
        self.assertIn("definition", result)
        self.assertEqual(result["definition"].nodes[1].type, "telegram")

    async def test_assist_workflow_generates_for_actionable_multi_channel_prompt(self) -> None:
        service = LLMService(client=object(), model="test-model")
        service.generate_workflow_definition = AsyncMock(
            return_value=GeneratedWorkflowResult(
                definition=WorkflowDefinition.model_validate(_valid_definition()),
                name="Lead Nurture",
            )
        )

        result = await service.assist_workflow(
            prompt=(
                "create a nurturing workflow for 14 days lead generation from different apps "
                "like watsapp, telegram, slack, gmail, likendin"
            ),
        )

        self.assertEqual(result["mode"], "generate")
        self.assertEqual(result["questions"], [])
        service.generate_workflow_definition.assert_awaited_once()

    async def test_assist_workflow_includes_recent_chat_context_in_generation_prompt(self) -> None:
        service = LLMService(client=object(), model="test-model")
        service.generate_workflow_definition = AsyncMock(
            return_value=GeneratedWorkflowResult(
                definition=WorkflowDefinition.model_validate(_valid_definition()),
                name="Contextual Flow",
            )
        )

        await service.assist_workflow(
            prompt="Add a delay before telegram send",
            conversation_state={
                "recent_messages": [
                    {"role": "user", "content": "Use webhook trigger and validate payload"},
                    {"role": "assistant", "content": "Noted. We can use webhook + code node."},
                ],
            },
        )

        generated_prompt = service.generate_workflow_definition.await_args.args[0]
        self.assertIn("Recent chat context:", generated_prompt)
        self.assertIn("user: Use webhook trigger and validate payload", generated_prompt)

    async def test_assist_workflow_includes_memory_anchors_in_generation_prompt(self) -> None:
        service = LLMService(client=object(), model="test-model")
        service.generate_workflow_definition = AsyncMock(
            return_value=GeneratedWorkflowResult(
                definition=WorkflowDefinition.model_validate(_valid_definition()),
                name="Memory Anchored Flow",
            )
        )

        await service.assist_workflow(
            prompt="Add retry after HTTP request",
            conversation_state={
                "last_referenced_nodes": ["sync_ticket_http", "http_success_check"],
                "last_unresolved_question": "Should retry happen before or after routing?",
                "last_accepted_workflow_signature": "sig-accepted-123",
            },
        )

        generated_prompt = service.generate_workflow_definition.await_args.args[0]
        self.assertIn("Conversation memory anchors:", generated_prompt)
        self.assertIn("Last referenced nodes: sync_ticket_http, http_success_check", generated_prompt)
        self.assertIn("Last unresolved question: Should retry happen before or after routing?", generated_prompt)
        self.assertIn("Last accepted workflow signature: sig-accepted-123", generated_prompt)

    def test_sanitize_ask_response_format_removes_markdown_bold_markers(self) -> None:
        raw = "**Workflow Brief**\n* First step\n**Parameters**: Use field."
        sanitized = LLMService._sanitize_ask_response_format(raw)
        self.assertNotIn("**", sanitized)
        self.assertIn("Workflow Brief", sanitized)
        self.assertIn("- First step", sanitized)

    def test_infer_requested_channels_handles_common_typos(self) -> None:
        requested = LLMService._infer_requested_channel_node_types(
            "send nurture via watsapp, telegram, slack, gmail and likendin"
        )
        self.assertIn("whatsapp", requested)
        self.assertIn("linkedin", requested)
        self.assertIn("telegram", requested)
        self.assertIn("slack_send_message", requested)
        self.assertIn("send_gmail_message", requested)

    async def test_assist_workflow_strips_credentials_from_generated_output(self) -> None:
        payload = {
            "definition": {
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
                        "type": "send_gmail_message",
                        "label": "Send Email",
                        "position": {"x": 360, "y": 150},
                        "config": {
                            "credential_id": "super-secret-id",
                            "to": "{{email}}",
                            "cc": "",
                            "bcc": "",
                            "reply_to": "",
                            "subject": "Hello",
                            "body": "Hi there",
                            "image": "",
                            "is_html": False,
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
        }
        fake_client = _FakeClient(responses=[json.dumps(payload)])
        service = LLMService(client=fake_client, model="test-model")

        result = await service.assist_workflow(
            prompt="Manually send email updates",
        )

        self.assertEqual(result["mode"], "generate")
        generated_definition = result["definition"]
        gmail_node = next(node for node in generated_definition.nodes if node.type == "send_gmail_message")
        self.assertEqual(gmail_node.config.get("credential_id"), "")

    async def test_assist_workflow_modify_returns_structural_change_summary(self) -> None:
        current_definition = WorkflowDefinition.model_validate(_valid_definition())
        updated_payload = {
            "definition": {
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
                        "config": {"credential_id": "", "message": "Updated message", "parse_mode": ""},
                    },
                    {
                        "id": "n3",
                        "type": "delay",
                        "label": "Wait",
                        "position": {"x": 520, "y": 120},
                        "config": {"amount": "1", "unit": "hours", "until_datetime": ""},
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
                    },
                    {
                        "id": "e2",
                        "source": "n2",
                        "target": "n3",
                        "sourceHandle": None,
                        "targetHandle": None,
                        "branch": None,
                    },
                ],
            }
        }
        fake_client = _FakeClient(responses=[json.dumps(updated_payload)])
        service = LLMService(client=fake_client, model="test-model")

        result = await service.assist_workflow(
            prompt="update existing workflow to add delay before completion",
            current_definition=current_definition,
            conversation_state={
                "last_mode": "modify",
            },
        )

        self.assertEqual(result["mode"], "modify")
        self.assertIsInstance(result["change_summary"], str)
        self.assertTrue(result["change_summary"])
        self.assertIsNone(result["name"])

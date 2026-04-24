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

    def test_validate_generated_workflow_accepts_definition_wrapper(self) -> None:
        raw_content = json.dumps({"definition": _valid_definition()})

        definition, _ = LLMService.validate_generated_workflow(raw_content)

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

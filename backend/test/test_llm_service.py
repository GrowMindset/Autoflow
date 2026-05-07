from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.workflows import NODE_CONFIG_DEFAULTS, WorkflowDefinition
from app.services.llm_service import GeneratedWorkflowResult, LLMService, WorkflowGenerationError


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
        self.assertNotIn("if_else parameters", result["assistant_message"])

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

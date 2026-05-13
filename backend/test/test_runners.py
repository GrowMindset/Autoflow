import unittest
import os
import tempfile
from unittest.mock import MagicMock, patch

import httpx
from app.execution.runners.nodes import ai_agent
from app.execution.runners.nodes.aggregate import AggregateRunner
from app.execution.runners.nodes.add_gmail_label import AddGmailLabelRunner
from app.execution.runners.nodes.ai_agent import AIAgentRunner
from app.execution.runners.nodes.create_gmail_draft import CreateGmailDraftRunner
from app.execution.runners.nodes.delay import DelayRunner
from app.execution.runners.nodes.datetime_format import DateTimeFormatRunner
from app.execution.runners.nodes.dummy import DummyNodeRunner
from app.execution.runners.nodes.file_read import FileReadRunner
from app.execution.runners.nodes.file_write import FileWriteRunner
from app.execution.runners.nodes.filter import FilterRunner
from app.execution.runners.nodes.http_request import HttpRequestRunner
from app.execution.runners.nodes.if_else import IfElseRunner
from app.execution.runners.nodes.limit import LimitRunner
from app.execution.runners.nodes.merge import MergeRunner
from app.execution.runners.nodes.read_google_docs import ReadGoogleDocsRunner
from app.execution.runners.nodes.read_google_sheets import ReadGoogleSheetsRunner
from app.execution.runners.nodes.search_update_google_sheets import SearchUpdateGoogleSheetsRunner
from app.execution.runners.nodes.send_gmail_message import SendGmailMessageRunner
from app.execution.runners.nodes.sort import SortRunner
from app.execution.runners.nodes.split_in import SplitInRunner
from app.execution.runners.nodes.split_out import SplitOutRunner
from app.execution.runners.nodes.switch import SwitchRunner
from app.execution.runners.triggers.form_trigger import FormTriggerRunner
from app.execution.runners.triggers.manual_trigger import ManualTriggerRunner
from app.execution.runners.triggers.schedule_trigger import ScheduleTriggerRunner
from app.execution.runners.triggers.webhook_trigger import WebhookTriggerRunner
from app.execution.runners.triggers.workflow_trigger import WorkflowTriggerRunner


class RunnerTests(unittest.TestCase):
    @staticmethod
    def _public_resolver(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    def test_ai_agent_runner_returns_output_key(self):
        runner = AIAgentRunner()
        runner._run_provider_completion = lambda *args, **kwargs: "hello world"

        result = runner.run(
            config={
                "provider": "openai",
                "model": "gpt-4o-mini",
                "credential_id": "cred-1",
                "system_prompt": "You are helpful.",
                "command": "Say hello",
            },
            input_data=None,
            context={"resolved_credentials": {"cred-1": "secret"}},
        )

        self.assertEqual(result["output"], "hello world")
        self.assertNotIn("ai_response", result)

    def test_ai_agent_runner_prefers_inline_chat_model_api_key(self):
        original_get_provider = ai_agent.get_provider
        fake_provider = None

        class FakeProvider:
            def __init__(self, api_key):
                self.api_key = api_key

            async def complete(self, *args, **kwargs):
                return "done"

        def fake_get_provider(provider, api_key):
            nonlocal fake_provider
            fake_provider = FakeProvider(api_key)
            return fake_provider

        ai_agent.get_provider = fake_get_provider
        try:
            runner = AIAgentRunner()
            runner.run(
                config={"command": "Hello"},
                input_data={
                    "chat_model": {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "credential_id": "cred-inline",
                        "api_key": "inline-secret",
                        "options": {"temperature": 0.1},
                    }
                },
                context={"resolved_credentials": {"cred-inline": "context-secret"}},
            )
        finally:
            ai_agent.get_provider = original_get_provider

        self.assertIsNotNone(fake_provider)
        self.assertEqual(fake_provider.api_key, "inline-secret")

    def test_ai_agent_runner_maps_authentication_error(self):
        runner = AIAgentRunner()

        class AuthenticationError(Exception):
            pass

        def fake_call_openai(*args, **kwargs):
            raise AuthenticationError("bad key")

        runner._run_provider_completion = fake_call_openai

        with self.assertRaisesRegex(
            ValueError,
            "Invalid API key. Check your saved credential.",
        ):
            runner.run(
                config={
                    "provider": "openai",
                    "credential_id": "cred-1",
                    "command": "Hello",
                },
                input_data=None,
                context={"resolved_credentials": {"cred-1": "secret"}},
            )

    def test_ai_agent_runner_maps_rate_limit_error(self):
        runner = AIAgentRunner()

        class RateLimitError(Exception):
            pass

        def fake_call_groq(*args, **kwargs):
            raise RateLimitError("slow down")

        runner._run_provider_completion = fake_call_groq

        with self.assertRaisesRegex(
            ValueError,
            "Rate limit reached. Wait and retry.",
        ):
            runner.run(
                config={
                    "provider": "groq",
                    "credential_id": "cred-1",
                    "command": "Hello",
                },
                input_data=None,
                context={"resolved_credentials": {"cred-1": "secret"}},
            )

    def test_ai_agent_runner_maps_timeout_error(self):
        runner = AIAgentRunner()

        class APITimeoutError(Exception):
            pass

        def fake_call_openai(*args, **kwargs):
            raise APITimeoutError("timed out")

        runner._run_provider_completion = fake_call_openai

        with self.assertRaisesRegex(
            ValueError,
            "Request timed out. Try again.",
        ):
            runner.run(
                config={
                    "provider": "openai",
                    "credential_id": "cred-1",
                    "command": "Hello",
                },
                input_data=None,
                context={"resolved_credentials": {"cred-1": "secret"}},
            )

    def test_ai_agent_runner_enhances_low_quality_response(self):
        runner = AIAgentRunner()
        call_payloads = []

        def fake_call_openai(*args, **kwargs):
            call_payloads.append(kwargs)
            if len(call_payloads) == 1:
                return "As an AI language model, {{customer_name}}."
            return "Order update:\n- Customer: Asha\n- Status: In transit"

        runner._run_provider_completion = fake_call_openai

        result = runner.run(
            config={
                "provider": "openai",
                "credential_id": "cred-1",
                "system_prompt": "You are helpful.",
                "command": "Reply to customer with order status",
            },
            input_data=None,
            context={"resolved_credentials": {"cred-1": "secret"}},
        )

        self.assertEqual(len(call_payloads), 2)
        self.assertIn(
            "response quality editor",
            call_payloads[1]["system_prompt"].lower(),
        )
        self.assertEqual(
            result["output"],
            "Order update:\n- Customer: Asha\n- Status: In transit",
        )
        self.assertNotIn("ai_response", result)

    def test_ai_agent_runner_falls_back_when_response_enhancement_fails(self):
        runner = AIAgentRunner()
        call_count = 0

        def fake_call_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "As an AI language model, {{customer_name}}."
            raise RuntimeError("refinement failed")

        runner._run_provider_completion = fake_call_openai

        result = runner.run(
            config={
                "provider": "openai",
                "credential_id": "cred-1",
                "command": "Reply to customer with order status",
            },
            input_data=None,
            context={"resolved_credentials": {"cred-1": "secret"}},
        )

        self.assertEqual(call_count, 2)
        self.assertEqual(result["output"], "As an AI language model, {{customer_name}}.")

    def test_ai_agent_runner_skips_enhancement_when_disabled(self):
        runner = AIAgentRunner()
        call_count = 0

        def fake_call_openai(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return "As an AI language model, {{customer_name}}."

        runner._run_provider_completion = fake_call_openai

        result = runner.run(
            config={
                "provider": "openai",
                "credential_id": "cred-1",
                "command": "Reply to customer with order status",
                "response_enhancement": "off",
            },
            input_data=None,
            context={"resolved_credentials": {"cred-1": "secret"}},
        )

        self.assertEqual(call_count, 1)
        self.assertEqual(result["output"], "As an AI language model, {{customer_name}}.")

    def test_if_else_runner_true_branch(self):
        runner = IfElseRunner()
        result = runner.run(
            config={"field": "status", "operator": "equals", "value": "paid"},
            input_data={"status": "paid", "amount": 500},
        )
        self.assertEqual(result, {"status": "paid", "amount": 500, "_branch": "true"})

    def test_if_else_runner_supports_field_to_field_comparison(self):
        runner = IfElseRunner()
        result = runner.run(
            config={
                "field": "status",
                "operator": "equals",
                "value_mode": "field",
                "value_field": "expected_status",
            },
            input_data={"status": "PAID", "expected_status": "PAID"},
        )
        self.assertEqual(result["_branch"], "true")

    def test_if_else_runner_supports_case_insensitive_compare(self):
        runner = IfElseRunner()
        result = runner.run(
            config={
                "field": "status",
                "operator": "contains",
                "value": "paid",
                "case_sensitive": False,
            },
            input_data={"status": "PAID_SUCCESS"},
        )
        self.assertEqual(result["_branch"], "true")

    def test_if_else_runner_supports_and_success(self):
        runner = IfElseRunner()
        result = runner.run(
            config={
                "condition_type": "AND",
                "conditions": [
                    {"field": "status", "operator": "equals", "value": "active"},
                    {"field": "priority", "operator": "greater_than", "value": 5},
                ],
            },
            input_data={"status": "active", "priority": 8},
        )
        self.assertEqual(result["_branch"], "true")

    def test_if_else_runner_supports_and_failure(self):
        runner = IfElseRunner()
        result = runner.run(
            config={
                "condition_type": "AND",
                "conditions": [
                    {"field": "status", "operator": "equals", "value": "active"},
                    {"field": "priority", "operator": "greater_than", "value": 5},
                ],
            },
            input_data={"status": "active", "priority": 3},
        )
        self.assertEqual(result["_branch"], "false")

    def test_if_else_runner_supports_or_success(self):
        runner = IfElseRunner()
        result = runner.run(
            config={
                "condition_type": "OR",
                "conditions": [
                    {"field": "country", "operator": "equals", "value": "India"},
                    {"field": "country", "operator": "equals", "value": "USA"},
                ],
            },
            input_data={"country": "USA"},
        )
        self.assertEqual(result["_branch"], "true")

    def test_if_else_runner_supports_or_failure(self):
        runner = IfElseRunner()
        result = runner.run(
            config={
                "condition_type": "OR",
                "conditions": [
                    {"field": "country", "operator": "equals", "value": "India"},
                    {"field": "country", "operator": "equals", "value": "USA"},
                ],
            },
            input_data={"country": "Canada"},
        )
        self.assertEqual(result["_branch"], "false")

    def test_send_gmail_runner_normalizes_recipient_lists(self):
        recipients = SendGmailMessageRunner._split_and_validate_emails(
            'Asha <asha@example.com>; mina@example.com\nli@example.org',
            field_name="to",
        )
        self.assertEqual(
            recipients,
            ["asha@example.com", "mina@example.com", "li@example.org"],
        )

    def test_send_gmail_runner_rejects_unresolved_recipient_templates(self):
        with self.assertRaisesRegex(ValueError, "unresolved template"):
            SendGmailMessageRunner._split_and_validate_emails(
                "{{form.student_email}}",
                field_name="to",
            )

    def test_send_gmail_runner_rejects_invalid_recipient_email(self):
        with self.assertRaisesRegex(ValueError, "invalid email"):
            SendGmailMessageRunner._split_and_validate_emails(
                "not-an-email",
                field_name="to",
            )

    def test_send_gmail_runner_accepts_dict_recipient_value(self):
        recipients = SendGmailMessageRunner._split_and_validate_emails(
            {"email": "student@example.com"},
            field_name="to",
        )
        self.assertEqual(recipients, ["student@example.com"])

    def test_send_gmail_runner_accepts_list_of_recipient_dicts(self):
        recipients = SendGmailMessageRunner._split_and_validate_emails(
            [{"email": "one@example.com"}, {"user_email": "two@example.com"}],
            field_name="to",
        )
        self.assertEqual(recipients, ["one@example.com", "two@example.com"])

    def test_create_gmail_draft_runner_creates_draft(self):
        runner = CreateGmailDraftRunner()
        credential = {
            "provider": "google_oauth",
            "access_token": "token",
            "refresh_token": "refresh",
            "email": "sender@example.com",
        }
        drafts_resource = MagicMock()
        drafts_resource.create.return_value.execute.return_value = {"id": "r123456789"}
        users_resource = MagicMock()
        users_resource.drafts.return_value = drafts_resource
        service = MagicMock()
        service.users.return_value = users_resource

        with patch(
            "app.execution.runners.nodes.create_gmail_draft.build_google_user_credentials",
            return_value=object(),
        ), patch("app.execution.runners.nodes.create_gmail_draft.build", return_value=service):
            result = runner.run(
                config={
                    "credential_id": "cred-1",
                    "to": "recipient@example.com",
                    "subject": "Draft subject",
                    "body": "Draft body text",
                },
                input_data={"upstream": True},
                context={"resolved_credential_data": {"cred-1": credential}},
            )

        drafts_resource.create.assert_called_once()
        self.assertEqual(result["draft_id"], "r123456789")
        self.assertEqual(result["gmail_draft_id"], "r123456789")
        self.assertEqual(result["upstream"], True)
        self.assertIn("created_at", result)

    def test_add_gmail_label_runner_finds_existing_label_and_modifies_message(self):
        runner = AddGmailLabelRunner()
        credential = {
            "provider": "google_oauth",
            "access_token": "token",
            "refresh_token": "refresh",
        }
        labels_resource = MagicMock()
        labels_resource.list.return_value.execute.return_value = {
            "labels": [{"id": "Label_123", "name": "Autoflow/Processed"}]
        }
        messages_resource = MagicMock()
        messages_resource.modify.return_value.execute.return_value = {"id": "msg123"}
        users_resource = MagicMock()
        users_resource.labels.return_value = labels_resource
        users_resource.messages.return_value = messages_resource
        service = MagicMock()
        service.users.return_value = users_resource

        with patch(
            "app.execution.runners.nodes.add_gmail_label.build_google_user_credentials",
            return_value=object(),
        ), patch("app.execution.runners.nodes.add_gmail_label.build", return_value=service):
            result = runner.run(
                config={
                    "credential_id": "cred-1",
                    "message_id": "msg123",
                    "label_name": "Autoflow/Processed",
                },
                input_data=None,
                context={"resolved_credential_data": {"cred-1": credential}},
            )

        labels_resource.create.assert_not_called()
        messages_resource.modify.assert_called_once_with(
            userId="me",
            id="msg123",
            body={"addLabelIds": ["Label_123"]},
        )
        self.assertEqual(result["message_id"], "msg123")
        self.assertEqual(result["label_id"], "Label_123")
        self.assertEqual(result["label_name"], "Autoflow/Processed")
        self.assertIn("applied_at", result)

    def test_add_gmail_label_runner_creates_missing_label(self):
        runner = AddGmailLabelRunner()
        labels_resource = MagicMock()
        labels_resource.list.return_value.execute.return_value = {"labels": []}
        labels_resource.create.return_value.execute.return_value = {"id": "Label_New"}
        messages_resource = MagicMock()
        messages_resource.modify.return_value.execute.return_value = {"id": "msg123"}
        users_resource = MagicMock()
        users_resource.labels.return_value = labels_resource
        users_resource.messages.return_value = messages_resource
        service = MagicMock()
        service.users.return_value = users_resource

        with patch(
            "app.execution.runners.nodes.add_gmail_label.build_google_user_credentials",
            return_value=object(),
        ), patch("app.execution.runners.nodes.add_gmail_label.build", return_value=service):
            result = runner.run(
                config={
                    "credential_id": "cred-1",
                    "message_id": "msg123",
                    "label_name": "Autoflow/Processed",
                },
                input_data={},
                context={
                    "resolved_credential_data": {
                        "cred-1": {"provider": "google_oauth", "access_token": "token"}
                    }
                },
            )

        labels_resource.create.assert_called_once()
        self.assertEqual(result["label_id"], "Label_New")

    def test_sheets_search_update_prefers_header_name_over_column_letters(self):
        headers = ["Email", "Status", "Notes"]
        index = SearchUpdateGoogleSheetsRunner._resolve_column_index("Email", headers)
        self.assertEqual(index, 1)

    def test_sheets_search_update_resolves_column_letter_without_headers(self):
        index = SearchUpdateGoogleSheetsRunner._resolve_column_index("B", [])
        self.assertEqual(index, 2)

    def test_sheets_search_update_coerce_bool_handles_string_false(self):
        self.assertFalse(
            SearchUpdateGoogleSheetsRunner._coerce_bool("false", default=True)
        )
        self.assertFalse(
            SearchUpdateGoogleSheetsRunner._coerce_bool("0", default=True)
        )
        self.assertTrue(
            SearchUpdateGoogleSheetsRunner._coerce_bool("true", default=False)
        )

    def test_sheets_search_update_preserves_blank_headers_for_column_position(self):
        headers = SearchUpdateGoogleSheetsRunner._ensure_headers(
            service=None,
            spreadsheet_id="",
            sheet_name="",
            headers=["Email", "", "Status"],
            search_column="Status",
            update_columns=["Status"],
            ensure_columns=[],
            input_data={},
            auto_create_headers=False,
        )
        index = SearchUpdateGoogleSheetsRunner._resolve_column_index("Status", headers)
        self.assertEqual(index, 3)

    def test_sheets_search_update_collect_update_pairs_from_mappings(self):
        pairs = SearchUpdateGoogleSheetsRunner._collect_update_pairs(
            {
                "update_mappings": [
                    {"column": "Status", "value": "Processed"},
                    {"column": "Notes", "value": "{{ai.summary}}"},
                ]
            }
        )
        self.assertEqual(
            pairs,
            [
                {"column": "Status", "value": "Processed"},
                {"column": "Notes", "value": "{{ai.summary}}"},
            ],
        )

    def test_sheets_search_update_collect_update_pairs_supports_legacy_fallback(self):
        pairs = SearchUpdateGoogleSheetsRunner._collect_update_pairs(
            {"update_column": "Status", "update_value": "Processed"}
        )
        self.assertEqual(
            pairs,
            [{"column": "Status", "value": "Processed"}],
        )

    def test_sheets_search_update_normalize_operation_supports_aliases(self):
        self.assertEqual(
            SearchUpdateGoogleSheetsRunner._normalize_operation({"operation": "overwrite"}),
            "overwrite_row",
        )
        self.assertEqual(
            SearchUpdateGoogleSheetsRunner._normalize_operation({"operation": "delete_column"}),
            "delete_columns",
        )

    def test_sheets_search_update_resolve_spreadsheet_id_from_url(self):
        spreadsheet_id = SearchUpdateGoogleSheetsRunner._resolve_spreadsheet_id(
            {
                "spreadsheet_source_type": "url",
                "spreadsheet_url": "https://docs.google.com/spreadsheets/d/1aBcD-12345_xyz/edit#gid=0",
            }
        )
        self.assertEqual(spreadsheet_id, "1aBcD-12345_xyz")

    def test_sheets_search_update_converts_complex_values_to_cell_text(self):
        self.assertEqual(
            SearchUpdateGoogleSheetsRunner._to_sheet_cell_value(["Java", "Python", "FastAPI"]),
            "Java, Python, FastAPI",
        )
        self.assertEqual(
            SearchUpdateGoogleSheetsRunner._to_sheet_cell_value({"score": 10}),
            '{"score": 10}',
        )

    def test_read_google_sheets_resolves_spreadsheet_id_from_url(self):
        spreadsheet_id = ReadGoogleSheetsRunner._resolve_spreadsheet_id(
            {
                "spreadsheet_source_type": "url",
                "spreadsheet_url": "https://docs.google.com/spreadsheets/d/1aBcD-12345_xyz/edit#gid=0",
            }
        )
        self.assertEqual(spreadsheet_id, "1aBcD-12345_xyz")

    def test_read_google_sheets_normalizes_duplicate_headers(self):
        headers = ReadGoogleSheetsRunner._normalize_headers(["Name", "Name", "", "Email"])
        self.assertEqual(headers, ["Name", "Name_2", "column_3", "Email"])

    def test_read_google_sheets_maps_rows_using_header_mode(self):
        class _FakeRequest:
            def __init__(self, payload):
                self.payload = payload

            def execute(self):
                return self.payload

        class _FakeValuesApi:
            def __init__(self, payload):
                self.payload = payload

            def get(self, **kwargs):
                return _FakeRequest(self.payload)

        class _FakeSpreadsheetsApi:
            def __init__(self, payload):
                self.payload = payload

            def values(self):
                return _FakeValuesApi(self.payload)

        class _FakeSheetsService:
            def __init__(self, payload):
                self.payload = payload

            def spreadsheets(self):
                return _FakeSpreadsheetsApi(self.payload)

        runner = ReadGoogleSheetsRunner()
        fake_service = _FakeSheetsService(
            {
                "values": [
                    ["Name", "Email"],
                    ["Asha", "asha@example.com"],
                    ["Mina", "mina@example.com"],
                ]
            }
        )

        with (
            patch.object(ReadGoogleSheetsRunner, "_build_sheets_service", return_value=fake_service),
            patch.object(ReadGoogleSheetsRunner, "_resolve_sheet_name", return_value="Leads"),
        ):
            result = runner.run(
                config={
                    "credential_id": "cred-1",
                    "spreadsheet_source_type": "id",
                    "spreadsheet_id": "sheet-id-1",
                    "sheet_name": "Leads",
                    "first_row_as_header": True,
                },
                input_data={"source": "test"},
                context={
                    "resolved_credential_data": {
                        "cred-1": {
                            "provider": "google_oauth",
                            "access_token": "token",
                        }
                    }
                },
            )

        self.assertEqual(result["source"], "test")
        self.assertEqual(result["google_sheets_row_count"], 2)
        self.assertEqual(
            result["google_sheets_headers"],
            ["Name", "Email"],
        )
        self.assertEqual(
            result["google_sheets_data"],
            [
                {"Name": "Asha", "Email": "asha@example.com"},
                {"Name": "Mina", "Email": "mina@example.com"},
            ],
        )

    def test_read_google_sheets_supports_plain_rows_and_max_rows(self):
        class _FakeRequest:
            def __init__(self, payload):
                self.payload = payload

            def execute(self):
                return self.payload

        class _FakeValuesApi:
            def __init__(self, payload):
                self.payload = payload

            def get(self, **kwargs):
                return _FakeRequest(self.payload)

        class _FakeSpreadsheetsApi:
            def __init__(self, payload):
                self.payload = payload

            def values(self):
                return _FakeValuesApi(self.payload)

        class _FakeSheetsService:
            def __init__(self, payload):
                self.payload = payload

            def spreadsheets(self):
                return _FakeSpreadsheetsApi(self.payload)

        runner = ReadGoogleSheetsRunner()
        fake_service = _FakeSheetsService(
            {
                "values": [
                    ["A", "B"],
                    [],
                    ["C", "D"],
                ]
            }
        )

        with (
            patch.object(ReadGoogleSheetsRunner, "_build_sheets_service", return_value=fake_service),
            patch.object(ReadGoogleSheetsRunner, "_resolve_sheet_name", return_value="Sheet1"),
        ):
            result = runner.run(
                config={
                    "credential_id": "cred-1",
                    "spreadsheet_source_type": "id",
                    "spreadsheet_id": "sheet-id-1",
                    "sheet_name": "Sheet1",
                    "first_row_as_header": False,
                    "include_empty_rows": False,
                    "max_rows": "2",
                },
                input_data=None,
                context={
                    "resolved_credential_data": {
                        "cred-1": {
                            "provider": "google_oauth",
                            "access_token": "token",
                        }
                    }
                },
            )

        self.assertEqual(result["google_sheets_data"], [["A", "B"], ["C", "D"]])
        self.assertEqual(result["google_sheets_row_count"], 2)

    def test_read_google_docs_resolves_document_id_from_url(self):
        document_id = ReadGoogleDocsRunner._resolve_document_id(
            {
                "document_source_type": "url",
                "document_url": "https://docs.google.com/document/d/1AbCdEfGhIJkLmNoPqRstUvWxYz1234567890/edit",
            }
        )
        self.assertEqual(document_id, "1AbCdEfGhIJkLmNoPqRstUvWxYz1234567890")

    def test_read_google_docs_extracts_text_and_applies_max_characters(self):
        class _FakeRequest:
            def __init__(self, payload):
                self.payload = payload

            def execute(self):
                return self.payload

        class _FakeDocumentsApi:
            def __init__(self, payload):
                self.payload = payload

            def get(self, **kwargs):
                return _FakeRequest(self.payload)

        class _FakeDocsService:
            def __init__(self, payload):
                self.payload = payload

            def documents(self):
                return _FakeDocumentsApi(self.payload)

        runner = ReadGoogleDocsRunner()
        fake_service = _FakeDocsService(
            {
                "documentId": "doc-123",
                "title": "Weekly Notes",
                "revisionId": "rev-5",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [
                                    {"textRun": {"content": "Hello "}},
                                    {"textRun": {"content": "team\n"}},
                                ]
                            }
                        },
                        {
                            "table": {
                                "tableRows": [
                                    {
                                        "tableCells": [
                                            {
                                                "content": [
                                                    {
                                                        "paragraph": {
                                                            "elements": [
                                                                {"textRun": {"content": "Cell A\n"}}
                                                            ]
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        },
                    ]
                },
            }
        )

        with patch.object(ReadGoogleDocsRunner, "_build_docs_service", return_value=fake_service):
            result = runner.run(
                config={
                    "credential_id": "cred-1",
                    "document_source_type": "id",
                    "document_id": "doc-123",
                    "max_characters": "8",
                    "include_raw_json": True,
                },
                input_data={"source": "test"},
                context={
                    "resolved_credential_data": {
                        "cred-1": {
                            "provider": "google_oauth",
                            "access_token": "token",
                        }
                    }
                },
            )

        self.assertEqual(result["source"], "test")
        self.assertTrue(result["google_docs_read"])
        self.assertEqual(result["google_docs_document_id"], "doc-123")
        self.assertEqual(result["google_docs_title"], "Weekly Notes")
        self.assertEqual(result["google_docs_text"], "Hello te")
        self.assertEqual(result["google_docs_text_length"], 8)
        self.assertEqual(result["google_docs_text_full_length"], 18)
        self.assertTrue(result["google_docs_text_truncated"])
        self.assertIn("google_docs_document", result)

    def test_read_google_docs_rejects_invalid_source_type(self):
        runner = ReadGoogleDocsRunner()
        with self.assertRaisesRegex(ValueError, "document_source_type"):
            runner.run(
                config={
                    "credential_id": "cred-1",
                    "document_source_type": "folder",
                    "document_id": "doc-123",
                },
                input_data={},
                context={
                    "resolved_credential_data": {
                        "cred-1": {
                            "provider": "google_oauth",
                            "access_token": "token",
                        }
                    }
                },
            )

    def test_delay_runner_resolves_amount_and_unit(self):
        runner = DelayRunner()
        seconds = runner._resolve_delay_seconds({"amount": "2", "unit": "minutes"})
        self.assertEqual(seconds, 120)

    def test_delay_runner_supports_days(self):
        runner = DelayRunner()
        seconds = runner._resolve_delay_seconds({"amount": "2", "unit": "days"})
        self.assertEqual(seconds, 172800)

    def test_delay_runner_supports_months_as_30_days(self):
        runner = DelayRunner()
        seconds = runner._resolve_delay_seconds({"amount": "1", "unit": "months"})
        self.assertEqual(seconds, 2592000)

    def test_delay_runner_supports_until_datetime(self):
        runner = DelayRunner()
        output = runner.run(
            config={"until_datetime": "1970-01-01T00:00:00Z"},
            input_data={"ok": True},
        )
        self.assertEqual(output["ok"], True)
        self.assertEqual(output["delay_seconds"], 0)

    def test_delay_runner_emits_run_at_for_positive_delay(self):
        runner = DelayRunner()
        output = runner.run(
            config={"amount": "1", "unit": "seconds"},
            input_data={"ok": True},
        )
        self.assertEqual(output["ok"], True)
        self.assertGreater(output["delay_seconds"], 0)
        self.assertIn("delay_run_at", output)

    def test_delay_runner_supports_until_datetime_mode_with_timezone(self):
        runner = DelayRunner()
        output = runner.run(
            config={
                "wait_mode": "until_datetime",
                "until_datetime": "2035-01-01T09:00:00",
                "timezone": "Asia/Kolkata",
            },
            input_data={"ok": True},
        )
        self.assertEqual(output["wait_mode"], "until_datetime")
        self.assertGreaterEqual(float(output["delay_seconds"]), 0.0)

    def test_delay_runner_rejects_until_datetime_mode_without_datetime(self):
        runner = DelayRunner()
        with self.assertRaisesRegex(ValueError, "requires 'until_datetime'"):
            runner.run(
                config={"wait_mode": "until_datetime"},
                input_data={"ok": True},
            )

    def test_if_else_runner_raises_for_unknown_operator(self):
        runner = IfElseRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"field": "status", "operator": "is_empty", "value": ""},
                input_data={"status": "paid"},
            )

    def test_if_else_runner_rejects_empty_conditions(self):
        runner = IfElseRunner()
        with self.assertRaisesRegex(ValueError, "missing 'field'"):
            runner.run(
                config={"condition_type": "AND", "conditions": []},
                input_data={"status": "paid"},
            )

    def test_if_else_runner_rejects_invalid_condition_type(self):
        runner = IfElseRunner()
        with self.assertRaisesRegex(ValueError, "condition_type"):
            runner.run(
                config={
                    "condition_type": "XOR",
                    "conditions": [
                        {"field": "status", "operator": "equals", "value": "paid"},
                    ],
                },
                input_data={"status": "paid"},
            )

    def test_switch_runner_matches_first_case(self):
        runner = SwitchRunner()
        result = runner.run(
            config={
                "field": "country",
                "cases": [
                    {"label": "india", "operator": "equals", "value": "IN"},
                    {"label": "usa", "operator": "equals", "value": "US"},
                ],
                "default_case": "default",
            },
            input_data={"country": "US"},
        )
        self.assertEqual(result, {"country": "US", "_branch": "usa"})

    def test_switch_runner_uses_default_case(self):
        runner = SwitchRunner()
        result = runner.run(
            config={
                "field": "country",
                "cases": [
                    {"label": "india", "operator": "equals", "value": "IN"},
                ],
            },
            input_data={"country": "JP"},
        )
        self.assertEqual(result, {"country": "JP", "_branch": "default"})

    def test_switch_runner_requires_value_for_case(self):
        runner = SwitchRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={
                    "field": "country",
                    "cases": [{"label": "india", "operator": "equals"}],
                },
                input_data={"country": "IN"},
            )

    def test_merge_runner_merges_branch_outputs(self):
        runner = MergeRunner()
        result = runner.run(
            config={"mode": "append"},
            input_data=[
                {"country": "IN", "tax": 18},
                None,
                {"country": "US", "tax": 10},
            ],
        )
        self.assertEqual(
            result,
            {"merged": [{"country": "IN", "tax": 18}, {"country": "US", "tax": 10}]},
        )

    def test_merge_runner_rejects_empty_input(self):
        runner = MergeRunner()
        with self.assertRaises(ValueError):
            runner.run(config={}, input_data=[])

    def test_merge_runner_default_append_for_single_branch(self):
        runner = MergeRunner()
        result = runner.run(
            config={},
            input_data=[{"country": "IN", "tax": 18}],
        )
        self.assertEqual(result, {"merged": [{"country": "IN", "tax": 18}]})

    def test_merge_runner_choose_input_1(self):
        runner = MergeRunner()
        result = runner.run(
            config={"mode": "choose_input_1", "output_key": "merged"},
            input_data=[
                {"handle": "input1", "data": {"a": 1}},
                {"handle": "input2", "data": {"b": 2}},
            ],
        )
        self.assertEqual(result, {"a": 1})

    def test_merge_runner_choose_branch_by_handle(self):
        runner = MergeRunner()
        result = runner.run(
            config={"mode": "choose_branch", "choose_branch": "input3", "output_key": "merged"},
            input_data=[
                {"handle": "input1", "data": {"a": 1}},
                {"handle": "input2", "data": {"b": 2}},
                {"handle": "input3", "data": {"c": 3}},
            ],
        )
        self.assertEqual(result, {"c": 3})

    def test_merge_runner_choose_branch_missing_handle_fails_fast(self):
        runner = MergeRunner()
        with self.assertRaisesRegex(ValueError, "selected handle 'input9'"):
            runner.run(
                config={"mode": "choose_branch", "choose_branch": "input9"},
                input_data=[
                    {"handle": "input1", "data": {"a": 1}},
                    {"handle": "input2", "data": {"b": 2}},
                ],
            )

    def test_merge_runner_choose_branch_missing_handle_supports_explicit_legacy_fallback(self):
        runner = MergeRunner()
        result = runner.run(
            config={
                "mode": "choose_branch",
                "choose_branch": "input9",
                "allow_missing_branch_fallback": True,
            },
            input_data=[
                {"handle": "input2", "data": {"b": 2}},
                {"handle": "input1", "data": {"a": 1}},
            ],
        )
        # Legacy fallback keeps backward-compatible "first available handle" behavior.
        self.assertEqual(result, {"b": 2})

    def test_merge_runner_choose_branch_rejects_handle_outside_input_count(self):
        runner = MergeRunner()
        with self.assertRaisesRegex(ValueError, "exceeds input_count=2"):
            runner.run(
                config={
                    "mode": "choose_branch",
                    "choose_branch": "input3",
                    "input_count": 2,
                },
                input_data=[
                    {"handle": "input1", "data": {"a": 1}},
                    {"handle": "input2", "data": {"b": 2}},
                ],
            )

    def test_merge_runner_combine_mode_merges_objects_for_downstream(self):
        runner = MergeRunner()
        result = runner.run(
            config={"mode": "combine"},
            input_data=[
                {"document_id": "doc_123", "status": "ok"},
                None,
                {"sentiment": "negative"},
            ],
        )
        self.assertEqual(
            result,
            {
                "document_id": "doc_123",
                "status": "ok",
                "sentiment": "negative",
            },
        )

    def test_merge_runner_combine_mode_rejects_non_object_items(self):
        runner = MergeRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"mode": "combine"},
                input_data=[{"ok": True}, "raw-string"],
            )

    def test_merge_runner_combine_by_position_inner_join(self):
        runner = MergeRunner()
        result = runner.run(
            config={"mode": "combine_by_position", "join_type": "inner", "output_key": "merged"},
            input_data=[
                {"handle": "input1", "data": [{"id": 1, "a": "x"}, {"id": 2, "a": "y"}]},
                {"handle": "input2", "data": [{"id": 1, "b": 10}]},
            ],
        )
        self.assertEqual(result, {"merged": [{"id": 1, "a": "x", "b": 10}]})

    def test_merge_runner_combine_by_position_requires_both_configured_handles(self):
        runner = MergeRunner()
        with self.assertRaisesRegex(
            ValueError,
            "requires connected inputs for handle\\(s\\): input2",
        ):
            runner.run(
                config={
                    "mode": "combine_by_position",
                    "join_type": "inner",
                    "input_1_handle": "input1",
                    "input_2_handle": "input2",
                },
                input_data=[
                    {"handle": "input1", "data": [{"id": 1, "a": "x"}]},
                ],
            )

    def test_merge_runner_combine_by_fields_outer_join(self):
        runner = MergeRunner()
        result = runner.run(
            config={
                "mode": "combine_by_fields",
                "join_type": "outer",
                "input_1_field": "email",
                "input_2_field": "email",
                "output_key": "merged",
            },
            input_data=[
                {"handle": "input1", "data": [{"email": "a@test.com", "name": "A"}]},
                {"handle": "input2", "data": [{"email": "a@test.com", "score": 90}, {"email": "b@test.com", "score": 75}]},
            ],
        )
        self.assertEqual(
            result,
            {
                "merged": [
                    {"email": "a@test.com", "name": "A", "score": 90},
                    {"email": "b@test.com", "score": 75},
                ]
            },
        )

    def test_merge_runner_combine_by_fields_rejects_handle_outside_input_count(self):
        runner = MergeRunner()
        with self.assertRaisesRegex(ValueError, "input_2_handle exceeds input_count=2"):
            runner.run(
                config={
                    "mode": "combine_by_fields",
                    "input_count": 2,
                    "input_1_handle": "input1",
                    "input_2_handle": "input3",
                    "input_1_field": "email",
                    "input_2_field": "email",
                },
                input_data=[
                    {"handle": "input1", "data": [{"email": "a@test.com"}]},
                    {"handle": "input3", "data": [{"email": "a@test.com"}]},
                ],
            )

    def test_filter_runner_filters_array(self):
        runner = FilterRunner()
        result = runner.run(
            config={"input_key": "items", "field": "amount", "operator": "greater_than", "value": "500"},
            input_data={"items": [{"amount": 300}, {"amount": 700}, {"amount": 150}], "user": "A"}
        )
        self.assertEqual(result["items"], [{"amount": 700}])
        self.assertEqual(result["user"], "A")

    def test_filter_runner_supports_multiple_conditions_with_and_logic(self):
        runner = FilterRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "logic": "and",
                "conditions": [
                    {"field": "amount", "operator": "greater_than", "value": "500"},
                    {"field": "status", "operator": "equals", "value": "paid"},
                ],
            },
            input_data={
                "items": [
                    {"amount": 700, "status": "paid"},
                    {"amount": 700, "status": "pending"},
                    {"amount": 250, "status": "paid"},
                ]
            },
        )
        self.assertEqual(result["items"], [{"amount": 700, "status": "paid"}])

    def test_filter_runner_supports_multiple_conditions_with_or_logic(self):
        runner = FilterRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "logic": "or",
                "conditions": [
                    {"field": "amount", "operator": "greater_than", "value": "500"},
                    {"field": "status", "operator": "equals", "value": "urgent"},
                ],
            },
            input_data={
                "items": [
                    {"amount": 700, "status": "paid"},
                    {"amount": 250, "status": "urgent"},
                    {"amount": 250, "status": "pending"},
                ]
            },
        )
        self.assertEqual(
            result["items"],
            [{"amount": 700, "status": "paid"}, {"amount": 250, "status": "urgent"}],
        )

    def test_filter_runner_supports_mixed_condition_chaining(self):
        runner = FilterRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "conditions": [
                    {"field": "status", "operator": "equals", "value": "vip"},
                    {
                        "field": "amount",
                        "operator": "greater_than",
                        "value": "500",
                        "join_with_previous": "or",
                    },
                    {
                        "field": "country",
                        "operator": "equals",
                        "value": "IN",
                        "join_with_previous": "and",
                    },
                ],
            },
            input_data={
                "items": [
                    {"status": "vip", "amount": 100, "country": "US"},
                    {"status": "regular", "amount": 700, "country": "IN"},
                    {"status": "regular", "amount": 700, "country": "US"},
                    {"status": "regular", "amount": 300, "country": "IN"},
                ]
            },
        )
        self.assertEqual(
            result["items"],
            [
                {"status": "regular", "amount": 700, "country": "IN"},
            ],
        )

    def test_filter_runner_supports_number_data_type_precision(self):
        runner = FilterRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "conditions": [
                    {
                        "field": "amount",
                        "data_type": "number",
                        "operator": "greater_than_or_equals",
                        "value": "500",
                    }
                ],
            },
            input_data={"items": [{"amount": 499.99}, {"amount": 500}, {"amount": 700}]},
        )
        self.assertEqual(result["items"], [{"amount": 500}, {"amount": 700}])

    def test_filter_runner_supports_boolean_and_date_and_array_operators(self):
        runner = FilterRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "conditions": [
                    {
                        "field": "active",
                        "data_type": "boolean",
                        "operator": "is_true",
                    },
                    {
                        "field": "created_at",
                        "data_type": "date",
                        "operator": "after",
                        "value": "2026-05-01T00:00:00",
                        "join_with_previous": "and",
                    },
                    {
                        "field": "tags",
                        "data_type": "array",
                        "operator": "length_greater_than_or_equals",
                        "value": "2",
                        "join_with_previous": "and",
                    },
                ],
            },
            input_data={
                "items": [
                    {"active": True, "created_at": "2026-05-06T10:00:00", "tags": ["a", "b"]},
                    {"active": True, "created_at": "2026-04-01T10:00:00", "tags": ["a", "b"]},
                    {"active": False, "created_at": "2026-05-06T10:00:00", "tags": ["a", "b"]},
                    {"active": True, "created_at": "2026-05-06T10:00:00", "tags": ["a"]},
                ]
            },
        )
        self.assertEqual(
            result["items"],
            [{"active": True, "created_at": "2026-05-06T10:00:00", "tags": ["a", "b"]}],
        )

    def test_filter_runner_supports_exists_and_object_equals(self):
        runner = FilterRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "conditions": [
                    {
                        "field": "meta",
                        "data_type": "object",
                        "operator": "exists",
                    },
                    {
                        "field": "meta",
                        "data_type": "object",
                        "operator": "equals",
                        "value": '{"tier":"pro"}',
                        "join_with_previous": "and",
                    },
                    {
                        "field": "missing",
                        "data_type": "string",
                        "operator": "does_not_exist",
                        "join_with_previous": "and",
                    },
                ],
            },
            input_data={
                "items": [
                    {"meta": {"tier": "pro"}, "name": "A"},
                    {"meta": {"tier": "free"}, "name": "B"},
                    {"name": "C"},
                ]
            },
        )
        self.assertEqual(result["items"], [{"meta": {"tier": "pro"}, "name": "A"}])

    def test_filter_runner_supports_field_to_field_condition(self):
        runner = FilterRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "conditions": [
                    {
                        "field": "status",
                        "operator": "equals",
                        "value_mode": "field",
                        "value_field": "expected_status",
                    }
                ],
            },
            input_data={
                "items": [
                    {"status": "PAID", "expected_status": "PAID"},
                    {"status": "PENDING", "expected_status": "PAID"},
                ]
            },
        )
        self.assertEqual(
            result["items"],
            [{"status": "PAID", "expected_status": "PAID"}],
        )

    def test_filter_runner_supports_case_insensitive_contains(self):
        runner = FilterRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "conditions": [
                    {
                        "field": "status",
                        "operator": "contains",
                        "value": "paid",
                        "case_sensitive": False,
                    }
                ],
            },
            input_data={
                "items": [
                    {"status": "PAID_SUCCESS"},
                    {"status": "failed"},
                ]
            },
        )
        self.assertEqual(result["items"], [{"status": "PAID_SUCCESS"}])

    def test_filter_runner_returns_empty_for_no_matches(self):
        runner = FilterRunner()
        result = runner.run(
            config={"input_key": "items", "field": "status", "operator": "equals", "value": "ok"},
            input_data={"items": [{"status": "fail"}, {"status": "error"}]}
        )
        self.assertEqual(result["items"], [])

    def test_filter_runner_raises_for_non_list_input(self):
        runner = FilterRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "items", "field": "amount", "operator": "greater_than", "value": "10"},
                input_data={"items": "not-a-list"}
            )

    def test_filter_runner_rejects_unknown_operator(self):
        runner = FilterRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "items", "field": "amount", "operator": "between", "value": "10"},
                input_data={"items": [{"amount": 10}]},
            )

    def test_filter_runner_rejects_invalid_logic(self):
        runner = FilterRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={
                    "input_key": "items",
                    "logic": "xor",
                    "conditions": [
                        {"field": "amount", "operator": "greater_than", "value": "10"},
                    ],
                },
                input_data={"items": [{"amount": 10}]},
            )

    def test_limit_runner_limits_array_items(self):
        runner = LimitRunner()
        result = runner.run(
            config={"input_key": "items", "limit": "2", "offset": "0"},
            input_data={"items": [1, 2, 3, 4], "meta": {"source": "test"}},
        )
        self.assertEqual(result["items"], [1, 2])
        self.assertEqual(result["meta"], {"source": "test"})

    def test_limit_runner_applies_offset(self):
        runner = LimitRunner()
        result = runner.run(
            config={"input_key": "items", "limit": 2, "offset": 1},
            input_data={"items": ["a", "b", "c", "d"]},
        )
        self.assertEqual(result["items"], ["b", "c"])

    def test_limit_runner_supports_zero_limit(self):
        runner = LimitRunner()
        result = runner.run(
            config={"input_key": "items", "limit": 0, "offset": 0},
            input_data={"items": ["a", "b"]},
        )
        self.assertEqual(result["items"], [])

    def test_limit_runner_supports_end_mode(self):
        runner = LimitRunner()
        result = runner.run(
            config={"input_key": "items", "limit": 2, "offset": 0, "start_from": "end"},
            input_data={"items": ["a", "b", "c", "d"]},
        )
        self.assertEqual(result["items"], ["c", "d"])

    def test_limit_runner_supports_end_mode_with_offset(self):
        runner = LimitRunner()
        result = runner.run(
            config={"input_key": "items", "limit": 2, "offset": 1, "start_from": "end"},
            input_data={"items": ["a", "b", "c", "d", "e"]},
        )
        self.assertEqual(result["items"], ["c", "d"])

    def test_limit_runner_requires_list_input(self):
        runner = LimitRunner()
        with self.assertRaisesRegex(ValueError, "must be a list"):
            runner.run(
                config={"input_key": "items", "limit": 2},
                input_data={"items": "not-a-list"},
            )

    def test_limit_runner_rejects_invalid_integer_values(self):
        runner = LimitRunner()
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            runner.run(
                config={"input_key": "items", "limit": "abc"},
                input_data={"items": [1, 2, 3]},
            )

    def test_limit_runner_rejects_invalid_start_from_value(self):
        runner = LimitRunner()
        with self.assertRaisesRegex(ValueError, "must be 'start' or 'end'"):
            runner.run(
                config={"input_key": "items", "limit": 2, "start_from": "middle"},
                input_data={"items": [1, 2, 3]},
            )

    def test_sort_runner_sorts_primitive_array_ascending(self):
        runner = SortRunner()
        result = runner.run(
            config={"input_key": "items", "order": "asc", "data_type": "number"},
            input_data={"items": [5, 2, 9, 1]},
        )
        self.assertEqual(result["items"], [1, 2, 5, 9])

    def test_sort_runner_sorts_object_array_by_field_desc(self):
        runner = SortRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "sort_by": "score",
                "order": "desc",
                "data_type": "number",
            },
            input_data={
                "items": [
                    {"name": "A", "score": 7},
                    {"name": "B", "score": 10},
                    {"name": "C", "score": 3},
                ]
            },
        )
        self.assertEqual(
            result["items"],
            [
                {"name": "B", "score": 10},
                {"name": "A", "score": 7},
                {"name": "C", "score": 3},
            ],
        )

    def test_sort_runner_places_missing_values_first_when_configured(self):
        runner = SortRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "sort_by": "amount",
                "order": "asc",
                "data_type": "number",
                "nulls": "first",
            },
            input_data={
                "items": [
                    {"id": 1, "amount": 20},
                    {"id": 2},
                    {"id": 3, "amount": 10},
                ]
            },
        )
        self.assertEqual(
            result["items"],
            [
                {"id": 2},
                {"id": 3, "amount": 10},
                {"id": 1, "amount": 20},
            ],
        )

    def test_sort_runner_supports_case_insensitive_string_sort(self):
        runner = SortRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "sort_by": "name",
                "data_type": "string",
                "case_sensitive": False,
                "order": "asc",
            },
            input_data={
                "items": [
                    {"name": "zeta"},
                    {"name": "Alpha"},
                    {"name": "beta"},
                ]
            },
        )
        self.assertEqual(
            result["items"],
            [
                {"name": "Alpha"},
                {"name": "beta"},
                {"name": "zeta"},
            ],
        )

    def test_sort_runner_keeps_equal_values_stable_in_desc_order(self):
        runner = SortRunner()
        result = runner.run(
            config={
                "input_key": "items",
                "sort_by": "score",
                "order": "desc",
                "data_type": "number",
            },
            input_data={
                "items": [
                    {"id": "first", "score": 100},
                    {"id": "second", "score": 100},
                    {"id": "third", "score": 99},
                ]
            },
        )
        self.assertEqual(
            result["items"],
            [
                {"id": "first", "score": 100},
                {"id": "second", "score": 100},
                {"id": "third", "score": 99},
            ],
        )

    def test_sort_runner_rejects_invalid_data_type(self):
        runner = SortRunner()
        with self.assertRaisesRegex(ValueError, "data_type"):
            runner.run(
                config={"input_key": "items", "data_type": "currency"},
                input_data={"items": [1, 2, 3]},
            )

    def test_datetime_format_runner_reformats_date(self):
        runner = DateTimeFormatRunner()
        result = runner.run(
            config={"field": "order_date", "output_format": "%d %B %Y"},
            input_data={"order_date": "2026-04-07"}
        )
        self.assertEqual(result["order_date"], "07 April 2026")

    def test_datetime_format_runner_handles_bad_date(self):
        runner = DateTimeFormatRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"field": "order_date", "output_format": "%d %B %Y"},
                input_data={"order_date": "not-a-date"}
            )

    def test_datetime_format_runner_raises_on_null_field(self):
        runner = DateTimeFormatRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"field": "order_date", "output_format": "%d %B %Y"},
                input_data={"order_date": None}
            )

    def test_split_in_runner_emits_each_item(self):
        runner = SplitInRunner()
        result = runner.run(
            config={"input_key": "tickets"},
            input_data={"tickets": [{"id": 1}, {"id": 2}]}
        )
        self.assertEqual(result, [
            {"item": {"id": 1}, "_split_index": 0},
            {"item": {"id": 2}, "_split_index": 1}
        ])

    def test_split_in_runner_requires_list(self):
        runner = SplitInRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "tickets"},
                input_data={"tickets": "not-a-list"}
            )

    def test_split_in_runner_handles_empty_array(self):
        runner = SplitInRunner()
        result = runner.run(
            config={"input_key": "tickets"},
            input_data={"tickets": []},
        )
        self.assertEqual(result, [])

    def test_split_out_runner_reassembles_list(self):
        runner = SplitOutRunner()
        result = runner.run(
            config={"output_key": "processed_tickets"},
            input_data=[
                {"id": 1, "reply": "Hi", "_split_index": 0},
                {"id": 2, "reply": "Bye", "_split_index": 1}
            ]
        )
        self.assertEqual(result, {
            "processed_tickets": [
                {"id": 1, "reply": "Hi"},
                {"id": 2, "reply": "Bye"}
            ]
        })

    def test_split_out_runner_rejects_missing_split_index(self):
        runner = SplitOutRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={},
                input_data=[{"id": 1, "reply": "Hi"}]
            )

    def test_aggregate_runner_sum(self):
        runner = AggregateRunner()
        result = runner.run(
            config={"input_key": "orders", "field": "amount", "operation": "sum", "output_key": "totals"},
            input_data={"orders": [{"country": "IN", "amount": 300}, {"country": "IN", "amount": 700}, {"country": "US", "amount": 500}]}
        )
        self.assertEqual(result, {"totals": 1500.0})

    def test_aggregate_runner_count_no_group(self):
        runner = AggregateRunner()
        result = runner.run(
            config={"input_key": "orders", "operation": "count"},
            input_data={"orders": [{"id": 1}, {"id": 2}]}
        )
        self.assertEqual(result, {"result": 2})

    def test_aggregate_runner_invalid_operation(self):
        runner = AggregateRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "orders", "operation": "median"},
                input_data={"orders": [{"id": 1}]}
            )

    def test_aggregate_runner_non_numeric_field_raises(self):
        runner = AggregateRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "orders", "field": "amount", "operation": "sum"},
                input_data={"orders": [{"amount": "abc"}]}
            )

    def test_aggregate_runner_requires_field_for_avg(self):
        runner = AggregateRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "orders", "operation": "avg"},
                input_data={"orders": [{"amount": 5}]},
            )

    def test_aggregate_runner_empty_count_returns_zero(self):
        runner = AggregateRunner()
        result = runner.run(
            config={"input_key": "orders", "operation": "count"},
            input_data={"orders": []},
        )
        self.assertEqual(result, {"result": 0})

    def test_aggregate_runner_empty_min_raises(self):
        runner = AggregateRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "orders", "field": "amount", "operation": "min"},
                input_data={"orders": []},
            )

    def test_dummy_node_runner_passes_input_to_next_node(self):
        runner = DummyNodeRunner("send_gmail_message")
        result = runner.run(
            config={},
            input_data={"email": "user@example.com", "country": "IN"},
        )
        self.assertEqual(
            result,
            {
                "email": "user@example.com",
                "country": "IN",
                "dummy_node_executed": True,
                "dummy_node_type": "send_gmail_message",
                "dummy_node_message": "Dummy node executed for 'send_gmail_message'",
            },
        )

    def test_manual_trigger_runner_returns_metadata_with_no_input(self):
        runner = ManualTriggerRunner()
        result = runner.run(config={}, input_data=None)
        self.assertEqual(
            result,
            {"triggered": True, "trigger_type": "manual"},
        )

    def test_form_trigger_runner_preserves_payload(self):
        runner = FormTriggerRunner()
        result = runner.run(
            config={
                "fields": [
                    {"name": "name", "required": True},
                    {"name": "email", "required": True},
                ]
            },
            input_data={"name": "Asha", "email": "asha@example.com"},
        )
        self.assertEqual(
            result,
            {
                "triggered": True,
                "trigger_type": "form",
                "name": "Asha",
                "email": "asha@example.com",
            },
        )

    def test_form_trigger_runner_requires_field_definitions(self):
        runner = FormTriggerRunner()
        with self.assertRaisesRegex(
            ValueError, "config must have a non-empty 'fields' list"
        ):
            runner.run(config={}, input_data={"email": "asha@example.com"})

    def test_form_trigger_runner_requires_required_fields_in_payload(self):
        runner = FormTriggerRunner()
        with self.assertRaisesRegex(ValueError, "required field 'email'"):
            runner.run(
                config={
                    "fields": [
                        {"name": "email", "required": True},
                        {"name": "notes", "required": False},
                    ]
                },
                input_data={"notes": "hello"},
            )

    def test_form_trigger_runner_validates_new_field_types(self):
        runner = FormTriggerRunner()
        result = runner.run(
            config={
                "fields": [
                    {
                        "name": "priority",
                        "label": "Priority",
                        "type": "select",
                        "required": True,
                        "options": [{"label": "High", "value": "high"}],
                    },
                    {
                        "name": "contact_method",
                        "label": "Contact Method",
                        "type": "radio",
                        "options": [{"label": "Email", "value": "email"}],
                    },
                    {"name": "subscribed", "label": "Subscribed", "type": "checkbox"},
                    {"name": "appointment_date", "label": "Date", "type": "date"},
                    {"name": "meeting_time", "label": "Time", "type": "time"},
                    {"name": "scheduled_at", "label": "Scheduled", "type": "datetime"},
                    {"name": "website", "label": "Website", "type": "url"},
                    {"name": "contact", "label": "Contact", "type": "phone"},
                    {"name": "satisfaction", "label": "Satisfaction", "type": "rating", "max_stars": 5},
                ]
            },
            input_data={
                "priority": "high",
                "contact_method": "email",
                "subscribed": True,
                "appointment_date": "2026-05-15",
                "meeting_time": "14:30",
                "scheduled_at": "2026-05-15T14:30:00Z",
                "website": "https://example.com",
                "contact": "+919876543210",
                "satisfaction": 4,
            },
        )
        self.assertEqual(result["priority"], "high")
        self.assertEqual(result["subscribed"], True)
        self.assertEqual(result["satisfaction"], 4)

    def test_form_trigger_runner_rejects_invalid_new_field_values(self):
        runner = FormTriggerRunner()
        invalid_cases = [
            (
                {"name": "priority", "label": "Priority", "type": "select", "options": [{"label": "High", "value": "high"}]},
                {"priority": "low"},
                "configured options",
            ),
            (
                {"name": "subscribed", "label": "Subscribed", "type": "checkbox"},
                {"subscribed": "true"},
                "must be a boolean",
            ),
            (
                {"name": "appointment_date", "label": "Date", "type": "date"},
                {"appointment_date": "15-05-2026"},
                "YYYY-MM-DD",
            ),
            (
                {"name": "website", "label": "Website", "type": "url"},
                {"website": "not-a-url"},
                "valid URL",
            ),
            (
                {"name": "satisfaction", "label": "Satisfaction", "type": "rating"},
                {"satisfaction": 6},
                "integer from 1 to 5",
            ),
        ]
        for field, payload, message in invalid_cases:
            with self.subTest(field=field["type"]):
                with self.assertRaisesRegex(ValueError, message):
                    runner.run(config={"fields": [field]}, input_data=payload)

    def test_form_trigger_runner_accepts_checkbox_group(self):
        runner = FormTriggerRunner()
        result = runner.run(
            config={
                "fields": [
                    {
                        "name": "affected_platforms",
                        "label": "Affected Platforms",
                        "type": "checkbox_group",
                        "required": True,
                        "options": [
                            {"label": "Gmail", "value": "gmail"},
                            {"label": "Google Sheets", "value": "sheets"},
                            {"label": "Telegram", "value": "telegram"},
                        ],
                    }
                ]
            },
            input_data={"affected_platforms": ["gmail", "telegram"]},
        )
        self.assertEqual(result["affected_platforms"], ["gmail", "telegram"])

    def test_form_trigger_runner_rejects_invalid_checkbox_group(self):
        runner = FormTriggerRunner()
        field = {
            "name": "affected_platforms",
            "label": "Affected Platforms",
            "type": "checkbox_group",
            "required": True,
            "options": [
                {"label": "Gmail", "value": "gmail"},
                {"label": "Telegram", "value": "telegram"},
            ],
        }

        with self.assertRaisesRegex(ValueError, "at least one selected option"):
            runner.run(config={"fields": [field]}, input_data={"affected_platforms": []})

        with self.assertRaisesRegex(ValueError, "must be a list"):
            runner.run(config={"fields": [field]}, input_data={"affected_platforms": "gmail"})

        with self.assertRaisesRegex(ValueError, "configured options"):
            runner.run(config={"fields": [field]}, input_data={"affected_platforms": ["slack"]})

    def test_webhook_trigger_runner_sets_webhook_metadata(self):
        runner = WebhookTriggerRunner()
        result = runner.run(
            config={"ignored": True},
            input_data={"event": "order.created"},
        )
        self.assertEqual(
            result,
            {
                "triggered": True,
                "trigger_type": "webhook",
                "event": "order.created",
            },
        )

    def test_schedule_trigger_runner_sets_schedule_metadata(self):
        runner = ScheduleTriggerRunner()
        result = runner.run(
            config={
                "minute": "*/5",
                "hour": "*",
            },
            input_data={"scheduled_at": "2026-01-01T00:00:00Z"},
        )
        self.assertEqual(
            result,
            {
                "triggered": True,
                "trigger_type": "schedule",
                "scheduled_at": "2026-01-01T00:00:00Z",
            },
        )

    def test_workflow_trigger_runner_sets_workflow_metadata(self):
        runner = WorkflowTriggerRunner()
        result = runner.run(
            config={"source_workflow": "orders-sync"},
            input_data={"source_id": "wf-1"},
        )
        self.assertEqual(
            result,
            {
                "triggered": True,
                "trigger_type": "workflow",
                "source_id": "wf-1",
            },
        )

    def test_trigger_runners_reject_invalid_input_types(self):
        runners = [
            ManualTriggerRunner(),
            FormTriggerRunner(),
            ScheduleTriggerRunner(),
            WebhookTriggerRunner(),
            WorkflowTriggerRunner(),
        ]

        for runner in runners:
            with self.assertRaises(ValueError):
                if isinstance(runner, FormTriggerRunner):
                    runner.run(
                        config={"fields": [{"name": "email", "required": True}]},
                        input_data="not-a-dict",
                    )
                else:
                    runner.run(config={}, input_data="not-a-dict")

    def test_http_request_runner_applies_bearer_auth_and_parses_json(self):
        runner = HttpRequestRunner()
        fake_response = httpx.Response(
            200,
            json={"ok": True},
            headers={"content-type": "application/json"},
            request=httpx.Request("GET", "https://api.example.com/orders"),
        )

        with patch.object(HttpRequestRunner, "_perform_request", return_value=fake_response) as mocked:
            result = runner.run(
                config={
                    "url": "https://api.example.com/orders",
                    "method": "GET",
                    "auth_mode": "bearer",
                    "bearer_token": "test-token",
                    "response_format": "auto",
                },
                input_data={"source": "unit-test"},
                context={"outbound_host_resolver": self._public_resolver},
            )

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["response_body"], {"ok": True})
        self.assertEqual(result["http_response"]["body_kind"], "json")
        self.assertEqual(result["source"], "unit-test")
        self.assertEqual(
            mocked.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-token",
        )

    def test_http_request_runner_supports_api_key_auth_from_credential(self):
        runner = HttpRequestRunner()
        fake_response = httpx.Response(
            200,
            text="ok",
            headers={"content-type": "text/plain"},
            request=httpx.Request("GET", "https://api.example.com/ping?api_key=secret-key"),
        )

        with patch.object(HttpRequestRunner, "_perform_request", return_value=fake_response) as mocked:
            result = runner.run(
                config={
                    "url": "https://api.example.com/ping",
                    "method": "GET",
                    "auth_mode": "api_key",
                    "api_key_name": "api_key",
                    "api_key_in": "query",
                    "credential_id": "cred-1",
                    "response_format": "text",
                },
                input_data=None,
                context={
                    "outbound_host_resolver": self._public_resolver,
                    "resolved_credential_data": {
                        "cred-1": {"api_key": "secret-key"},
                    }
                },
            )

        self.assertEqual(result["response_body"], "ok")
        self.assertEqual(mocked.call_args.kwargs["query"]["api_key"], "secret-key")

    def test_http_request_runner_raises_on_http_error_by_default(self):
        runner = HttpRequestRunner()
        fake_response = httpx.Response(
            500,
            text="Internal server error",
            headers={"content-type": "text/plain"},
            request=httpx.Request("POST", "https://api.example.com/orders"),
        )

        with patch.object(HttpRequestRunner, "_perform_request", return_value=fake_response):
            with self.assertRaisesRegex(ValueError, "500"):
                runner.run(
                    config={
                        "url": "https://api.example.com/orders",
                        "method": "POST",
                        "body_type": "json",
                        "body_json": '{"name":"demo"}',
                    },
                    input_data=None,
                    context={"outbound_host_resolver": self._public_resolver},
                )

    def test_http_request_runner_blocks_localhost_targets(self):
        runner = HttpRequestRunner()
        with self.assertRaisesRegex(ValueError, "private networks are blocked"):
            runner.run(
                config={
                    "url": "http://localhost:8080/health",
                    "method": "GET",
                },
                input_data=None,
                context={},
            )

    def test_http_request_runner_can_allow_private_network_targets_via_env(self):
        runner = HttpRequestRunner()
        fake_response = httpx.Response(
            200,
            json={"ok": True},
            headers={"content-type": "application/json"},
            request=httpx.Request("GET", "http://localhost:8080/health"),
        )

        previous = os.environ.get("HTTP_REQUEST_ALLOW_PRIVATE_NETWORKS")
        os.environ["HTTP_REQUEST_ALLOW_PRIVATE_NETWORKS"] = "true"
        try:
            with patch.object(HttpRequestRunner, "_perform_request", return_value=fake_response):
                result = runner.run(
                    config={
                        "url": "http://localhost:8080/health",
                        "method": "GET",
                    },
                    input_data={},
                    context={},
                )
        finally:
            if previous is None:
                os.environ.pop("HTTP_REQUEST_ALLOW_PRIVATE_NETWORKS", None)
            else:
                os.environ["HTTP_REQUEST_ALLOW_PRIVATE_NETWORKS"] = previous

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["response_body"], {"ok": True})

    def test_http_request_runner_continue_on_fail_returns_error_response(self):
        runner = HttpRequestRunner()
        fake_response = httpx.Response(
            404,
            text="Not found",
            headers={"content-type": "text/plain"},
            request=httpx.Request("GET", "https://api.example.com/missing"),
        )

        with patch.object(HttpRequestRunner, "_perform_request", return_value=fake_response):
            result = runner.run(
                config={
                    "url": "https://api.example.com/missing",
                    "method": "GET",
                    "continue_on_fail": True,
                    "response_format": "text",
                },
                input_data={},
                context={"outbound_host_resolver": self._public_resolver},
            )

        self.assertEqual(result["status_code"], 404)
        self.assertFalse(result["http_response"]["ok"])
        self.assertEqual(result["response_body"], "Not found")

    def test_http_request_runner_uses_injected_resolver_without_live_dns(self):
        runner = HttpRequestRunner()
        fake_response = httpx.Response(
            200,
            json={"ok": True},
            headers={"content-type": "application/json"},
            request=httpx.Request("GET", "https://api.example.com/orders"),
        )

        with (
            patch(
                "app.execution.runners.nodes.http_request.socket.getaddrinfo",
                side_effect=AssertionError("live DNS should not be called"),
            ),
            patch.object(HttpRequestRunner, "_perform_request", return_value=fake_response),
        ):
            result = runner.run(
                config={
                    "url": "https://api.example.com/orders",
                    "method": "GET",
                },
                input_data={},
                context={
                    "outbound_host_resolver": self._public_resolver,
                },
            )

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["response_body"], {"ok": True})

    def test_http_request_runner_blocks_private_ip_from_injected_resolver(self):
        runner = HttpRequestRunner()
        with self.assertRaisesRegex(ValueError, "private networks are blocked"):
            runner.run(
                config={
                    "url": "https://api.example.com/orders",
                    "method": "GET",
                },
                input_data={},
                context={
                    "outbound_host_resolver": lambda host, port: ["127.0.0.1"],
                },
            )

    def test_http_request_runner_rejects_non_callable_injected_resolver(self):
        runner = HttpRequestRunner()
        with self.assertRaisesRegex(ValueError, "outbound_host_resolver must be callable"):
            runner.run(
                config={
                    "url": "https://api.example.com/orders",
                    "method": "GET",
                },
                input_data={},
                context={"outbound_host_resolver": "not-callable"},
            )

    def test_file_write_and_file_read_runners_handle_json_content(self):
        write_runner = FileWriteRunner()
        read_runner = FileReadRunner()

        with tempfile.TemporaryDirectory() as temp_dir:
            previous = os.environ.get("FILE_NODE_ALLOWED_BASE_DIRS")
            os.environ["FILE_NODE_ALLOWED_BASE_DIRS"] = temp_dir
            try:
                path = os.path.join(temp_dir, "report.json")
                write_result = write_runner.run(
                    config={
                        "file_path": path,
                        "content_source": "config",
                        "content_text": '{"ok": true, "count": 2}',
                        "input_format": "text",
                        "write_mode": "create",
                    },
                    input_data={},
                    context={},
                )

                self.assertEqual(write_result["file_write"]["path"], path)
                self.assertTrue(os.path.exists(path))

                read_result = read_runner.run(
                    config={
                        "file_path": path,
                        "parse_as": "json",
                    },
                    input_data={},
                    context={},
                )
            finally:
                if previous is None:
                    os.environ.pop("FILE_NODE_ALLOWED_BASE_DIRS", None)
                else:
                    os.environ["FILE_NODE_ALLOWED_BASE_DIRS"] = previous

        self.assertEqual(read_result["file_content"], {"ok": True, "count": 2})
        self.assertEqual(read_result["file_read"]["content_type"], "json")

    def test_file_write_runner_rejects_disallowed_extensions(self):
        runner = FileWriteRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_base = os.environ.get("FILE_NODE_ALLOWED_BASE_DIRS")
            previous_ext = os.environ.get("FILE_NODE_ALLOWED_EXTENSIONS")
            os.environ["FILE_NODE_ALLOWED_BASE_DIRS"] = temp_dir
            os.environ["FILE_NODE_ALLOWED_EXTENSIONS"] = "txt,json,csv"
            try:
                with self.assertRaisesRegex(ValueError, "not allowed"):
                    runner.run(
                        config={
                            "file_path": os.path.join(temp_dir, "payload.exe"),
                            "content_source": "config",
                            "content_text": "x",
                            "write_mode": "create",
                        },
                        input_data={},
                        context={},
                    )
            finally:
                if previous_base is None:
                    os.environ.pop("FILE_NODE_ALLOWED_BASE_DIRS", None)
                else:
                    os.environ["FILE_NODE_ALLOWED_BASE_DIRS"] = previous_base
                if previous_ext is None:
                    os.environ.pop("FILE_NODE_ALLOWED_EXTENSIONS", None)
                else:
                    os.environ["FILE_NODE_ALLOWED_EXTENSIONS"] = previous_ext


if __name__ == "__main__":
    unittest.main()

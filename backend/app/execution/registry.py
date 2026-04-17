from typing import Any


class RunnerRegistry:
    """Lazy runner lookup by workflow node type."""

    def __init__(self) -> None:
        self._runner_factories = {
            "manual_trigger": self._build_manual_trigger,
            "form_trigger": self._build_form_trigger,
            "schedule_trigger": self._build_schedule_trigger,
            "webhook_trigger": self._build_webhook_trigger,
            "if_else": self._build_if_else,
            "switch": self._build_switch,
            "filter": self._build_filter,
            "delay": self._build_delay,
            "merge": self._build_merge,
            "aggregate": self._build_aggregate,
            "datetime_format": self._build_datetime_format,
            "split_in": self._build_split_in,
            "split_out": self._build_split_out,
            "ai_agent": self._build_ai_agent,
            "chat_model_openai": self._build_chat_model_openai,
            "chat_model_groq": self._build_chat_model_groq,
            "get_gmail_message": self._build_get_gmail_message,
            "send_gmail_message": self._build_send_gmail_message,
            "create_google_sheets": self._build_create_google_sheets,
            "search_update_google_sheets": self._build_search_update_google_sheets,
            "create_google_docs": self._build_create_google_docs,
            "update_google_docs": self._build_update_google_docs,
            "telegram": self._build_telegram,
            "whatsapp": self._build_whatsapp,
            "slack_send_message": self._build_slack_send_message,
        }
        self._cache: dict[str, Any] = {}

    def get_runner(self, node_type: str) -> Any:
        if node_type in self._cache:
            return self._cache[node_type]

        factory = self._runner_factories.get(node_type)
        if factory is None:
            runner = self._build_dummy(node_type)
            self._cache[node_type] = runner
            return runner

        runner = factory()
        self._cache[node_type] = runner
        return runner

    @staticmethod
    def _build_dummy(node_type: str) -> Any:
        from app.execution.runners.nodes.dummy import DummyNodeRunner

        return DummyNodeRunner(node_type=node_type)

    @staticmethod
    def _build_manual_trigger() -> Any:
        from app.execution.runners.triggers.manual_trigger import (
            ManualTriggerRunner,
        )

        return ManualTriggerRunner()

    @staticmethod
    def _build_form_trigger() -> Any:
        from app.execution.runners.triggers.form_trigger import FormTriggerRunner

        return FormTriggerRunner()

    @staticmethod
    def _build_schedule_trigger() -> Any:
        from app.execution.runners.triggers.schedule_trigger import (
            ScheduleTriggerRunner,
        )

        return ScheduleTriggerRunner()

    @staticmethod
    def _build_webhook_trigger() -> Any:
        from app.execution.runners.triggers.webhook_trigger import (
            WebhookTriggerRunner,
        )

        return WebhookTriggerRunner()

    @staticmethod
    def _build_if_else() -> Any:
        from app.execution.runners.nodes.if_else import IfElseRunner

        return IfElseRunner()

    @staticmethod
    def _build_switch() -> Any:
        from app.execution.runners.nodes.switch import SwitchRunner

        return SwitchRunner()

    @staticmethod
    def _build_filter() -> Any:
        from app.execution.runners.nodes.filter import FilterRunner

        return FilterRunner()

    @staticmethod
    def _build_delay() -> Any:
        from app.execution.runners.nodes.delay import DelayRunner

        return DelayRunner()

    @staticmethod
    def _build_merge() -> Any:
        from app.execution.runners.nodes.merge import MergeRunner

        return MergeRunner()

    @staticmethod
    def _build_aggregate() -> Any:
        from app.execution.runners.nodes.aggregate import AggregateRunner

        return AggregateRunner()

    @staticmethod
    def _build_datetime_format() -> Any:
        from app.execution.runners.nodes.datetime_format import (
            DateTimeFormatRunner,
        )

        return DateTimeFormatRunner()

    @staticmethod
    def _build_split_in() -> Any:
        from app.execution.runners.nodes.split_in import SplitInRunner

        return SplitInRunner()

    @staticmethod
    def _build_split_out() -> Any:
        from app.execution.runners.nodes.split_out import SplitOutRunner

        return SplitOutRunner()


    @staticmethod
    def _build_ai_agent() -> Any:
        from app.execution.runners.nodes.ai_agent import AIAgentRunner

        return AIAgentRunner()

    @staticmethod
    def _build_chat_model_openai() -> Any:
        from app.execution.runners.nodes.chat_model_openai import (
            ChatModelOpenAIRunner,
        )

        return ChatModelOpenAIRunner()

    @staticmethod
    def _build_chat_model_groq() -> Any:
        from app.execution.runners.nodes.chat_model_groq import (
            ChatModelGroqRunner,
        )

        return ChatModelGroqRunner()

    @staticmethod
    def _build_get_gmail_message() -> Any:
        from app.execution.runners.nodes.get_gmail_message import GetGmailMessageRunner

        return GetGmailMessageRunner()

    @staticmethod
    def _build_send_gmail_message() -> Any:
        from app.execution.runners.nodes.send_gmail_message import SendGmailMessageRunner

        return SendGmailMessageRunner()

    @staticmethod
    def _build_create_google_sheets() -> Any:
        from app.execution.runners.nodes.create_google_sheets import CreateGoogleSheetsRunner

        return CreateGoogleSheetsRunner()

    @staticmethod
    def _build_search_update_google_sheets() -> Any:
        from app.execution.runners.nodes.search_update_google_sheets import (
            SearchUpdateGoogleSheetsRunner,
        )

        return SearchUpdateGoogleSheetsRunner()

    @staticmethod
    def _build_create_google_docs() -> Any:
        from app.execution.runners.nodes.create_google_docs import CreateGoogleDocsRunner

        return CreateGoogleDocsRunner()

    @staticmethod
    def _build_update_google_docs() -> Any:
        from app.execution.runners.nodes.update_google_docs import UpdateGoogleDocsRunner

        return UpdateGoogleDocsRunner()

    @staticmethod
    def _build_telegram() -> Any:
        from app.execution.runners.nodes.telegram import TelegramRunner

        return TelegramRunner()

    @staticmethod
    def _build_whatsapp() -> Any:
        from app.execution.runners.nodes.whatsapp import WhatsAppRunner

        return WhatsAppRunner()

    @staticmethod
    def _build_slack_send_message() -> Any:
        from app.execution.runners.nodes.slack_send_message import SlackSendMessageRunner

        return SlackSendMessageRunner()

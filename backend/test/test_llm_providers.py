from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.llm_providers import OpenAIProvider


class FakeOpenAIClient:
    calls: list[dict] = []

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    async def _create(self, **kwargs):
        self.__class__.calls.append(dict(kwargs))
        if "max_tokens" in kwargs:
            raise Exception(
                "Unsupported parameter: 'max_tokens' is not supported with this model. "
                "Use 'max_completion_tokens' instead."
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="done")
                )
            ]
        )

    async def close(self) -> None:
        return None


class LLMProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_provider_retries_with_max_completion_tokens(self) -> None:
        FakeOpenAIClient.calls = []
        provider = OpenAIProvider("test-key")

        with patch("openai.AsyncOpenAI", FakeOpenAIClient):
            result = await provider.complete(
                system_prompt="You are helpful.",
                user_prompt="Say done.",
                model="gpt-5.4",
                temperature=None,
                max_tokens=25,
            )

        self.assertEqual(result, "done")
        self.assertEqual(len(FakeOpenAIClient.calls), 2)
        self.assertEqual(FakeOpenAIClient.calls[0]["max_tokens"], 25)
        self.assertNotIn("max_tokens", FakeOpenAIClient.calls[1])
        self.assertEqual(FakeOpenAIClient.calls[1]["max_completion_tokens"], 25)

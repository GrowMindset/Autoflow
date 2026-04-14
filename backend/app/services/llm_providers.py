from __future__ import annotations

import abc
import inspect
from typing import Any


class BaseLLMProvider(abc.ABC):
    @abc.abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        raise NotImplementedError


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _build_chat_kwargs(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens:
        kwargs["max_tokens"] = int(max_tokens)
    return kwargs


def _extract_response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("Model response did not include any choices.")

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            item.text
            for item in content
            if getattr(item, "type", None) == "text" and getattr(item, "text", None)
        ]
        if text_parts:
            return "".join(text_parts)

    raise ValueError("Model response did not include text content.")


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        response = await _maybe_await(
            client.chat.completions.create(
                **_build_chat_kwargs(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
        )
        return _extract_response_text(response)


class GroqProvider(BaseLLMProvider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        from groq import Groq

        client = Groq(api_key=self.api_key)
        response = await _maybe_await(
            client.chat.completions.create(
                **_build_chat_kwargs(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
        )
        return _extract_response_text(response)


def get_provider(provider: str, api_key: str) -> BaseLLMProvider:
    normalized_provider = provider.strip().lower()
    if normalized_provider == "openai":
        return OpenAIProvider(api_key)
    if normalized_provider == "groq":
        return GroqProvider(api_key)

    raise ValueError(
        f"Unsupported LLM provider '{provider}'. "
        "Supported providers are: openai, groq."
    )

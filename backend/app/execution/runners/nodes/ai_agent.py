from __future__ import annotations

import asyncio
from typing import Any

from app.services.llm_providers import BaseLLMProvider, get_provider


class AIAgentRunner:
    """
    Executes an AI Agent node by calling a real LLM (OpenAI or Groq).

    Credential resolution is handled BEFORE this runner is invoked:
    `execute_workflow.py` fetches and decrypts all API keys in the async context
    and stores them in `runner_context["resolved_credentials"]` as a plain
    str(credential_id) -> api_key dict.  This runner just does a plain dict
    lookup — no async DB access needed here.

    Input handle layout
    -------------------
    - ``chat_model``  (from ChatModelOpenAIRunner / ChatModelGroqRunner)
      Carries: provider, model, credential_id, api_key, options{temperature, max_tokens}

    Config keys (fallback when no chat_model handle is connected)
    -------------------------------------------------------------
    - system_prompt  : str
    - command        : str   (the user prompt)
    - provider       : "openai" | "groq"   (default: "groq")
    - model          : str
    - credential_id  : str
    - temperature    : float (default: 0.7)
    - max_tokens     : int | None
    """

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}

        # ── Resolve chat model settings ──────────────────────────────────────
        chat_model_config: dict[str, Any] = {}
        if isinstance(input_data, dict):
            chat_model_config = input_data.get("chat_model") or {}

        provider    = (chat_model_config.get("provider")      or config.get("provider",    "groq")).lower()
        model       = (chat_model_config.get("model")         or config.get("model",        self._default_model(provider)))
        cred_id     = (chat_model_config.get("credential_id") or config.get("credential_id"))
        options     = chat_model_config.get("options") or {}
        temperature = float(options.get("temperature") or config.get("temperature", 0.7))
        max_tokens  = options.get("max_tokens") or config.get("max_tokens")

        system_prompt = config.get("system_prompt", "You are a helpful assistant.")
        command       = config.get("command", "")

        if not command:
            raise ValueError("AI Agent: 'command / prompt' is required but was not set.")

        # ── Look up the pre-resolved API key (no async needed) ───────────────
        api_key = chat_model_config.get("api_key")
        resolved: dict[str, str] = context.get("resolved_credentials") or {}
        if not api_key and cred_id:
            api_key = resolved.get(str(cred_id))

        if not api_key:
            raise ValueError(
                f"AI Agent: No API key found for credential_id='{cred_id}'. "
                "Make sure a credential is saved and selected in the connected "
                "Chat Model node (chat_model_openai or chat_model_groq)."
            )

        # ── Call the LLM ─────────────────────────────────────────────────────
        provider_instance = get_provider(provider, api_key)
        try:
            response_text = self._run_provider_completion(
                provider_instance,
                system_prompt=system_prompt,
                command=command,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise ValueError(self._format_provider_error(exc)) from exc

        result = {}
        if isinstance(input_data, dict):
            # Preserve upstream context but strip subnode configs to keep payload clean
            result.update({k: v for k, v in input_data.items() if k not in ("chat_model", "memory", "tool")})

        result["ai_response"] = response_text
        result["output"] = response_text
        result["ai_metadata"] = {
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt,
            "temperature": temperature,
        }

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _default_model(provider: str) -> str:
        # llama-3.3-70b-versatile is Groq's recommended production model (April 2026)
        return "llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o"

    @staticmethod
    def _format_provider_error(exc: Exception) -> str:
        error_name = exc.__class__.__name__
        if error_name == "AuthenticationError":
            return "Invalid API key. Check your saved credential."
        if error_name == "RateLimitError":
            return "Rate limit reached. Wait and retry."
        if error_name == "APITimeoutError":
            return "Request timed out. Try again."
        return str(exc)

    @staticmethod
    def _run_provider_completion(
        provider_instance: BaseLLMProvider,
        system_prompt: str,
        command: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        def _run() -> str:
            return asyncio.run(
                provider_instance.complete(
                    system_prompt=system_prompt,
                    user_prompt=command,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _run()

        # If we're already inside an event loop, run the provider in a dedicated
        # thread with its own event loop so synchronous execution still works.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run)
            return future.result()

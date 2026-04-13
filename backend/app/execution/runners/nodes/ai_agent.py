from __future__ import annotations

from typing import Any


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
      Carries: provider, model, credential_id, options{temperature, max_tokens}

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
        resolved: dict[str, str] = context.get("resolved_credentials") or {}
        api_key = resolved.get(str(cred_id)) if cred_id else None

        if not api_key:
            raise ValueError(
                f"AI Agent: No API key found for credential_id='{cred_id}'. "
                "Make sure a credential is saved and selected in the connected "
                "Chat Model node (chat_model_openai or chat_model_groq)."
            )

        # ── Call the LLM ─────────────────────────────────────────────────────
        if provider == "groq":
            response_text = self._call_groq(
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                command=command,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            response_text = self._call_openai(
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                command=command,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        return {
            "ai_response": response_text,
            "ai_metadata": {
                "provider": provider,
                "model": model,
                "system_prompt": system_prompt,
                "temperature": temperature,
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _default_model(provider: str) -> str:
        # llama-3.3-70b-versatile is Groq's recommended production model (April 2026)
        return "llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o"

    @staticmethod
    def _call_openai(
        api_key: str,
        model: str,
        system_prompt: str,
        command: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": command},
            ],
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = int(max_tokens)

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    @staticmethod
    def _call_groq(
        api_key: str,
        model: str,
        system_prompt: str,
        command: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        from groq import Groq

        client = Groq(api_key=api_key)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": command},
            ],
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = int(max_tokens)

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

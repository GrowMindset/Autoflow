from __future__ import annotations

import json
import asyncio
import re
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
    - response_enhancement : "auto" | "always" | "off" (default: "auto")
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
            draft_response = self._run_provider_completion(
                provider_instance,
                system_prompt=system_prompt,
                command=command,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise ValueError(self._format_provider_error(exc)) from exc

        response_text = self._verify_and_enhance_response(
            provider_instance=provider_instance,
            command=command,
            draft_response=draft_response,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            enhancement_mode=str(config.get("response_enhancement", "auto")).strip().lower(),
        )

        result = {}
        if isinstance(input_data, dict):
            # Preserve upstream context but strip subnode configs to keep payload clean
            result.update({k: v for k, v in input_data.items() if k not in ("chat_model", "memory", "tool")})

        try:
            parsed = json.loads(response_text)
            result["output"] = parsed  # now a dict, dot notation works
        except (json.JSONDecodeError, ValueError):
            result["output"] = response_text  # fallback to string
            
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

    def _verify_and_enhance_response(
        self,
        *,
        provider_instance: BaseLLMProvider,
        command: str,
        draft_response: str,
        model: str,
        temperature: float,
        max_tokens: int | None,
        enhancement_mode: str,
    ) -> str:
        normalized = self._normalize_response_text(draft_response)
        quality = self._assess_response_quality(normalized, command)

        should_enhance = enhancement_mode == "always" or (
            enhancement_mode not in {"off", "false", "none", "disabled"}
            and quality["should_enhance"]
        )
        if not should_enhance:
            return normalized

        refinement_system_prompt, refinement_command = self._build_refinement_prompts(
            command=command,
            draft_response=normalized,
            quality_issues=quality["issues"],
        )
        refinement_temperature = min(float(temperature), 0.35)
        try:
            refined = self._run_provider_completion(
                provider_instance,
                system_prompt=refinement_system_prompt,
                command=refinement_command,
                model=model,
                temperature=refinement_temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            return normalized

        refined_normalized = self._normalize_response_text(refined)
        if not refined_normalized:
            return normalized
        return refined_normalized

    @staticmethod
    def _normalize_response_text(response: str | None) -> str:
        text = str(response or "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = AIAgentRunner._strip_markdown_code_fences(text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _strip_markdown_code_fences(text: str) -> str:
        """
        Removes top-level markdown code fences from model output.

        Examples:
        - ```json\n{...}\n``` -> {...}
        - ```\nhello\n``` -> hello
        - AI Response\n```json\n{...}\n``` -> {...}
        """
        normalized = str(text or "").strip()
        if "```" not in normalized:
            return text

        fence_pattern = re.compile(r"```[^\n`]*\n?(?P<body>[\s\S]*?)```")
        matches = list(fence_pattern.finditer(normalized))
        if not matches:
            return text

        # Common case: exactly one fenced block with optional light prefix
        # like "AI Response:" and no meaningful suffix.
        if len(matches) == 1:
            match = matches[0]
            prefix = normalized[: match.start()].strip()
            suffix = normalized[match.end() :].strip()
            prefix_allowed = (
                not prefix
                or re.fullmatch(
                    r"(?:ai\s*response|response|output|result|json)\s*:?",
                    prefix,
                    flags=re.IGNORECASE,
                )
                is not None
            )
            if prefix_allowed and not suffix:
                return match.group("body").strip()

        # Fallback for strict full-text fenced payloads.
        match = re.match(
            r"^```[^\n]*\n(?P<body>[\s\S]*?)\n```$",
            normalized,
        )
        if match:
            return match.group("body").strip()

        inline_match = re.match(r"^```[^\n]*\s*(?P<body>[\s\S]*?)\s*```$", normalized)
        if inline_match:
            return inline_match.group("body").strip()

        return text

    def _assess_response_quality(self, response_text: str, command: str) -> dict[str, Any]:
        issues: list[str] = []

        if not response_text:
            return {"should_enhance": True, "issues": ["The response is empty."]}

        if re.search(r"\{\{[^}]+\}\}", response_text):
            issues.append("Contains unresolved template placeholders.")

        if re.search(r"\bas an ai (language )?model\b", response_text, re.IGNORECASE):
            issues.append("Contains meta language instead of a direct answer.")

        if self._looks_repetitive(response_text):
            issues.append("Contains repetitive text.")

        if self._looks_truncated(response_text):
            issues.append("Looks incomplete or abruptly truncated.")

        words = re.findall(r"\b\w+\b", response_text)
        if len(words) < 3 and not self._expects_brief_answer(command):
            issues.append("Too short to be useful for this instruction.")

        return {"should_enhance": bool(issues), "issues": issues}

    @staticmethod
    def _expects_brief_answer(command: str) -> bool:
        lowered = command.strip().lower()
        brief_patterns = (
            "one word",
            "single word",
            "yes or no",
            "true or false",
            "answer briefly",
            "short answer",
        )
        return any(pattern in lowered for pattern in brief_patterns)

    @staticmethod
    def _looks_repetitive(response_text: str) -> bool:
        lines = [line.strip().lower() for line in response_text.splitlines() if line.strip()]
        if len(lines) >= 3:
            unique_ratio = len(set(lines)) / len(lines)
            if unique_ratio < 0.7:
                return True

        sentences = [
            sentence.strip().lower()
            for sentence in re.split(r"[.!?]\s+", response_text)
            if sentence.strip()
        ]
        if len(sentences) >= 4:
            unique_sentence_ratio = len(set(sentences)) / len(sentences)
            if unique_sentence_ratio < 0.7:
                return True
        return False

    @staticmethod
    def _looks_truncated(response_text: str) -> bool:
        if not response_text:
            return True
        stripped = response_text.rstrip()
        incomplete_endings = ("...", "…", ":", "-", "(", "[", "{")
        if stripped.endswith(incomplete_endings):
            return True
        # Rough signal for unclosed markdown/code fences.
        if stripped.count("```") % 2 != 0:
            return True
        return False

    @staticmethod
    def _build_refinement_prompts(
        *,
        command: str,
        draft_response: str,
        quality_issues: list[str],
    ) -> tuple[str, str]:
        system_prompt = (
            "You are a response quality editor for workflow automations. "
            "Rewrite the draft so it is clear, useful, and polished like an n8n AI node output. "
            "Keep original meaning and facts. Do not invent data. "
            "Return only the improved final response."
        )
        issues_text = "; ".join(quality_issues) if quality_issues else "Improve clarity and formatting."
        user_prompt = (
            f"Original instruction:\n{command.strip()}\n\n"
            f"Draft response:\n{draft_response}\n\n"
            f"Issues to fix:\n{issues_text}\n\n"
            "Requirements:\n"
            "- Remove unresolved placeholders or meta talk.\n"
            "- Do not wrap output in markdown code fences.\n"
            "- Keep it concise but complete.\n"
            "- Use short bullets if multiple points are needed.\n"
            "- Return only the improved response."
        )
        return system_prompt, user_prompt

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

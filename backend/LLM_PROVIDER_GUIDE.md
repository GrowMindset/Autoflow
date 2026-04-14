# Adding a New LLM Provider

This repository uses a shared provider abstraction for LLM calls so that both the AI Agent node and the workflow generation service use the same integration layer.

## What to implement

1. Create a new provider class in `backend/app/services/llm_providers.py`.
2. Make the class inherit from `BaseLLMProvider`.
3. Implement the required method:

```python
async def complete(
    self,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int | None,
) -> str:
```

This method should:
- build a standard chat request using the provided prompt data,
- send it to the provider API,
- return only the model text output.

## Registering the provider

Add a single new branch to the `get_provider(provider: str, api_key: str)` factory in `backend/app/services/llm_providers.py`.

Example:

```python
if normalized_provider == "anthropic":
    return AnthropicProvider(api_key)
```

That's it.

## Why this works

- `AIAgentRunner` now resolves the provider using `get_provider(...)`.
- `LLMService` uses `OpenAIProvider` by default when no injected client is supplied.
- Every provider exposes the same `complete(...)` interface.

## Notes

- Do not add provider-specific wiring anywhere else.
- The only required changes are:
  1. the new provider class,
  2. one line in `get_provider(...)`.

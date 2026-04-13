from typing import Any

class ChatModelOpenAIRunner:
    """
    Passes through OpenAI chat model configuration.
    """

    def run(self, config: dict[str, Any], input_data: Any, context: dict[str, Any] = None) -> dict[str, Any]:
        return {
            "provider": "openai",
            "model": config.get("model", "gpt-4-turbo"),
            "credential_id": config.get("credential_id"),
            "options": {
                "temperature": config.get("temperature", 0.7),
                "max_tokens": config.get("max_tokens"),
            }
        }

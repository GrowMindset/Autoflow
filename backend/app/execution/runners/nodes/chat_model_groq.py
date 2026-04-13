from typing import Any

class ChatModelGroqRunner:
    """
    Passes through Groq chat model configuration.
    """

    def run(self, config: dict[str, Any], input_data: Any, context: dict[str, Any] = None) -> dict[str, Any]:
        return {
            "provider": "groq",
            "model": config.get("model", "llama-3.3-70b-versatile"),
            "credential_id": config.get("credential_id"),
            "options": {
                "temperature": config.get("temperature", 0.7),
                "max_tokens": config.get("max_tokens"),
            }
        }

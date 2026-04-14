import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.execution import DagExecutor
from app.execution.registry import RunnerRegistry
from app.execution.runners.nodes.ai_agent import AIAgentRunner

AIAgentRunner._run_provider_completion = staticmethod(lambda *args, **kwargs: "Mocked AI Response")

definition = {
    "nodes": [
        {"id": "n1", "type": "manual_trigger", "config": {}},
        {
            "id": "n2", 
            "type": "ai_agent", 
            "config": {
                "system_prompt": "Hello", 
                "command": "Say {{message}}",
                "provider": "openai",
                "credential_id": "dummy"
            }
        }
    ],
    "edges": [
        {"id": "e1", "source": "n1", "target": "n2"}
    ]
}

payload = {"message": "world"}

try:
    executor = DagExecutor()
    context = {"resolved_credentials": {"dummy": "fake_api_key"}}
    result = executor.execute(definition=definition, initial_payload=payload, runner_context=context)
    print("SUCCESS")
    print(result["terminal_outputs"])
except Exception as e:
    import traceback
    traceback.print_exc()

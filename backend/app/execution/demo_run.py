import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.execution import DagExecutor


SAMPLE_WORKFLOWS: dict[str, dict[str, Any]] = {
    "linear": {
        "definition": {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {
                    "id": "n2",
                    "type": "filter",
                    "config": {
                        "input_key": "items",
                        "field": "amount",
                        "operator": "greater_than",
                        "value": "500",
                    },
                },
                {
                    "id": "n3",
                    "type": "aggregate",
                    "config": {
                        "input_key": "items",
                        "operation": "count",
                        "output_key": "matched_count",
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
            ],
        },
        "payload": {
            "items": [
                {"amount": 300},
                {"amount": 700},
                {"amount": 900},
            ]
        },
    },
    "branch_merge": {
        "definition": {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {
                    "id": "n2",
                    "type": "if_else",
                    "config": {
                        "field": "status",
                        "operator": "equals",
                        "value": "paid",
                    },
                },
                {
                    "id": "n3",
                    "type": "filter",
                    "config": {
                        "input_key": "items",
                        "field": "amount",
                        "operator": "greater_than",
                        "value": "500",
                    },
                },
                {
                    "id": "n4",
                    "type": "aggregate",
                    "config": {
                        "input_key": "items",
                        "operation": "count",
                        "output_key": "failed_count",
                    },
                },
                {"id": "n5", "type": "merge", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3", "branch": "true"},
                {"id": "e3", "source": "n2", "target": "n4", "branch": "false"},
                {"id": "e4", "source": "n3", "target": "n5"},
                {"id": "e5", "source": "n4", "target": "n5"},
            ],
        },
        "payload": {
            "status": "paid",
            "items": [
                {"amount": 100},
                {"amount": 650},
                {"amount": 900},
            ],
        },
    },
    "split_loop": {
        "definition": {
            "nodes": [
                {"id": "n1", "type": "manual_trigger", "config": {}},
                {"id": "n2", "type": "split_in", "config": {"input_key": "items"}},
                {
                    "id": "n3",
                    "type": "if_else",
                    "config": {
                        "field": "item.status",
                        "operator": "equals",
                        "value": "paid",
                    },
                },
                {"id": "n4", "type": "split_out", "config": {"output_key": "results"}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2"},
                {"id": "e2", "source": "n2", "target": "n3"},
                {"id": "e3", "source": "n3", "target": "n4", "branch": "true"},
                {"id": "e4", "source": "n3", "target": "n4", "branch": "false"},
            ],
        },
        "payload": {
            "items": [
                {"id": 1, "status": "paid"},
                {"id": 2, "status": "failed"},
                {"id": 3, "status": "paid"},
            ]
        },
    },
}


def main() -> int:
    # sample_name = sys.argv[1] if len(sys.argv) > 1 else "linear"
    sample_name ="split_loop"
    sample = SAMPLE_WORKFLOWS.get(sample_name)
    if sample is None:
        print("Unknown sample workflow.")
        print(f"Available samples: {', '.join(sorted(SAMPLE_WORKFLOWS))}")
        return 1

    executor = DagExecutor()
    result = executor.execute(
        definition=sample["definition"],
        initial_payload=sample["payload"],
    )

    print(f"Sample: {sample_name}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

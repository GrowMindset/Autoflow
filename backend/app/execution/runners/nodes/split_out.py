from typing import Any, Dict, List


class SplitOutRunner:
    """
    Reassembles split branch outputs into a single list.

    Config shape:
    {
        "output_key": "processed_tickets"
    }

    Output shape:
    {
        "processed_tickets": [ ...cleaned branch outputs... ]
    }
    """

    def run(self, config: dict, input_data: list, context: dict[str, Any] = None) -> dict:
        if not isinstance(input_data, list):
            raise ValueError(
                f"SplitOutRunner: input_data must be a list, got {type(input_data).__name__}"
            )

        output_key = config.get("output_key", "results")

        indexed_items: List[Dict[str, Any]] = []
        for item in input_data:
            if not isinstance(item, dict):
                raise ValueError(
                    "SplitOutRunner: Each split output must be a dict"
                )
            if "_split_index" not in item:
                raise ValueError(
                    "SplitOutRunner: Each split output must contain '_split_index'"
                )
            indexed_items.append(item)

        indexed_items.sort(key=lambda entry: entry["_split_index"])
        merged = [
            {k: v for k, v in item.items() if k != "_split_index"}
            for item in indexed_items
        ]

        return {output_key: merged}


# Testing
# runner = SplitOutRunner()
# result = runner.run(
#     config={"output_key": "processed_tickets"},
#     input_data=[
#         {"id": 1, "reply": "Hi", "_split_index": 0},
#         {"id": 2, "reply": "Bye", "_split_index": 1}
#     ]
# )
# print(result)
# # → {"processed_tickets": [{"id": 1, "reply": "Hi"}, {"id": 2, "reply": "Bye"}]}

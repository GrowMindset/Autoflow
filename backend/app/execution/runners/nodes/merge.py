

from typing import Any

class MergeRunner:
    """
    Collects outputs from multiple incoming branches and merges
    them into a single list.

    Config shape:
    {}   ← no config needed at all

    Input shape (list of outputs from each branch):
    [
        {"country": "IN", "tax": 18},
        {"country": "US", "tax": 10},
        {"country": "UK", "tax": 20}
    ]

    Output shape:
    {
        "merged": [
            {"country": "IN", "tax": 18},
            {"country": "US", "tax": 10},
            {"country": "UK", "tax": 20}
        ]
    }
    """

    def run(self, config: dict, input_data: list, context: dict[str, Any] = None) -> dict:

        # --- Step 1: Validate input is a list ---
        if not isinstance(input_data, list):
            raise ValueError(
                "MergeRunner: input_data must be a list of branch outputs. "
                f"Got {type(input_data).__name__} instead. "
                "Make sure DAG executor is passing all branch outputs as a list."
            )

        if len(input_data) == 0:
            raise ValueError(
                "MergeRunner: input_data is empty. "
                "No branch outputs were collected to merge."
            )

        # --- Step 2: Filter out None values ---
        # Some branches may not have run (e.g. switch with no match on that path)
        valid_inputs = [item for item in input_data if item is not None]

        if len(valid_inputs) == 0:
            raise ValueError(
                "MergeRunner: All branch outputs are None. "
                "Nothing to merge."
            )

        # --- Step 3: Append all branch outputs into a list ---
        return {
            "merged": valid_inputs
        }
        
# Testing        
# runner = MergeRunner()

# # Test 1 — normal merge of 3 branches
# result = runner.run(
#     config={},
#     input_data=[
#         {"country": "IN", "tax": 18},
#         {"country": "US", "tax": 10},
#         {"country": "UK", "tax": 20}
#     ]
# )
# print(result)
# # → {"merged": [{"country": "IN", "tax": 18}, {"country": "US", "tax": 10}, {"country": "UK", "tax": 20}]}


# # Test 2 — one branch returned None (branch didn't run)
# result = runner.run(
#     config={},
#     input_data=[
#         {"country": "IN", "tax": 18},
#         None,                             # this branch didn't execute
#         {"country": "UK", "tax": 20}
#     ]
# )
# print(result)
# # → {"merged": [{"country": "IN", "tax": 18}, {"country": "UK", "tax": 20}]}

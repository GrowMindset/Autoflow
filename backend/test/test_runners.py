import unittest

from app.execution.runners.aggregate import AggregateRunner
from app.execution.runners.datetime_format import DateTimeFormatRunner
from app.execution.runners.filter import FilterRunner
from app.execution.runners.if_else import IfElseRunner
from app.execution.runners.merge import MergeRunner
from app.execution.runners.split_in import SplitInRunner
from app.execution.runners.split_out import SplitOutRunner
from app.execution.runners.switch import SwitchRunner


class RunnerTests(unittest.TestCase):
    def test_if_else_runner_true_branch(self):
        runner = IfElseRunner()
        result = runner.run(
            config={"field": "status", "operator": "equals", "value": "paid"},
            input_data={"status": "paid", "amount": 500},
        )
        self.assertEqual(result, {"status": "paid", "amount": 500, "_branch": "true"})

    def test_if_else_runner_raises_for_unknown_operator(self):
        runner = IfElseRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"field": "status", "operator": "is_empty", "value": ""},
                input_data={"status": "paid"},
            )

    def test_switch_runner_matches_first_case(self):
        runner = SwitchRunner()
        result = runner.run(
            config={
                "field": "country",
                "cases": [
                    {"label": "india", "operator": "equals", "value": "IN"},
                    {"label": "usa", "operator": "equals", "value": "US"},
                ],
                "default_case": "default",
            },
            input_data={"country": "US"},
        )
        self.assertEqual(result, {"country": "US", "_branch": "usa"})

    def test_switch_runner_uses_default_case(self):
        runner = SwitchRunner()
        result = runner.run(
            config={
                "field": "country",
                "cases": [
                    {"label": "india", "operator": "equals", "value": "IN"},
                ],
            },
            input_data={"country": "JP"},
        )
        self.assertEqual(result, {"country": "JP", "_branch": "default"})

    def test_switch_runner_requires_value_for_case(self):
        runner = SwitchRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={
                    "field": "country",
                    "cases": [{"label": "india", "operator": "equals"}],
                },
                input_data={"country": "IN"},
            )

    def test_merge_runner_merges_branch_outputs(self):
        runner = MergeRunner()
        result = runner.run(
            config={},
            input_data=[
                {"country": "IN", "tax": 18},
                None,
                {"country": "US", "tax": 10},
            ],
        )
        self.assertEqual(
            result,
            {"merged": [{"country": "IN", "tax": 18}, {"country": "US", "tax": 10}]},
        )

    def test_merge_runner_rejects_empty_input(self):
        runner = MergeRunner()
        with self.assertRaises(ValueError):
            runner.run(config={}, input_data=[])

    def test_filter_runner_filters_array(self):
        runner = FilterRunner()
        result = runner.run(
            config={"input_key": "items", "field": "amount", "operator": "greater_than", "value": "500"},
            input_data={"items": [{"amount": 300}, {"amount": 700}, {"amount": 150}], "user": "A"}
        )
        self.assertEqual(result["items"], [{"amount": 700}])
        self.assertEqual(result["user"], "A")

    def test_filter_runner_returns_empty_for_no_matches(self):
        runner = FilterRunner()
        result = runner.run(
            config={"input_key": "items", "field": "status", "operator": "equals", "value": "ok"},
            input_data={"items": [{"status": "fail"}, {"status": "error"}]}
        )
        self.assertEqual(result["items"], [])

    def test_filter_runner_raises_for_non_list_input(self):
        runner = FilterRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "items", "field": "amount", "operator": "greater_than", "value": "10"},
                input_data={"items": "not-a-list"}
            )

    def test_filter_runner_rejects_unknown_operator(self):
        runner = FilterRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "items", "field": "amount", "operator": "greater_than_or_equals", "value": "10"},
                input_data={"items": [{"amount": 10}]},
            )

    def test_datetime_format_runner_reformats_date(self):
        runner = DateTimeFormatRunner()
        result = runner.run(
            config={"field": "order_date", "output_format": "%d %B %Y"},
            input_data={"order_date": "2026-04-07"}
        )
        self.assertEqual(result["order_date"], "07 April 2026")

    def test_datetime_format_runner_handles_bad_date(self):
        runner = DateTimeFormatRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"field": "order_date", "output_format": "%d %B %Y"},
                input_data={"order_date": "not-a-date"}
            )

    def test_datetime_format_runner_raises_on_null_field(self):
        runner = DateTimeFormatRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"field": "order_date", "output_format": "%d %B %Y"},
                input_data={"order_date": None}
            )

    def test_split_in_runner_emits_each_item(self):
        runner = SplitInRunner()
        result = runner.run(
            config={"input_key": "tickets"},
            input_data={"tickets": [{"id": 1}, {"id": 2}]}
        )
        self.assertEqual(result, [
            {"item": {"id": 1}, "_split_index": 0},
            {"item": {"id": 2}, "_split_index": 1}
        ])

    def test_split_in_runner_requires_list(self):
        runner = SplitInRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "tickets"},
                input_data={"tickets": "not-a-list"}
            )

    def test_split_in_runner_handles_empty_array(self):
        runner = SplitInRunner()
        result = runner.run(
            config={"input_key": "tickets"},
            input_data={"tickets": []},
        )
        self.assertEqual(result, [])

    def test_split_out_runner_reassembles_list(self):
        runner = SplitOutRunner()
        result = runner.run(
            config={"output_key": "processed_tickets"},
            input_data=[
                {"id": 1, "reply": "Hi", "_split_index": 0},
                {"id": 2, "reply": "Bye", "_split_index": 1}
            ]
        )
        self.assertEqual(result, {
            "processed_tickets": [
                {"id": 1, "reply": "Hi"},
                {"id": 2, "reply": "Bye"}
            ]
        })

    def test_split_out_runner_rejects_missing_split_index(self):
        runner = SplitOutRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={},
                input_data=[{"id": 1, "reply": "Hi"}]
            )

    def test_aggregate_runner_sum(self):
        runner = AggregateRunner()
        result = runner.run(
            config={"input_key": "orders", "field": "amount", "operation": "sum", "output_key": "totals"},
            input_data={"orders": [{"country": "IN", "amount": 300}, {"country": "IN", "amount": 700}, {"country": "US", "amount": 500}]}
        )
        self.assertEqual(result, {"totals": 1500.0})

    def test_aggregate_runner_count_no_group(self):
        runner = AggregateRunner()
        result = runner.run(
            config={"input_key": "orders", "operation": "count"},
            input_data={"orders": [{"id": 1}, {"id": 2}]}
        )
        self.assertEqual(result, {"result": 2})

    def test_aggregate_runner_invalid_operation(self):
        runner = AggregateRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "orders", "operation": "median"},
                input_data={"orders": [{"id": 1}]}
            )

    def test_aggregate_runner_non_numeric_field_raises(self):
        runner = AggregateRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "orders", "field": "amount", "operation": "sum"},
                input_data={"orders": [{"amount": "abc"}]}
            )

    def test_aggregate_runner_requires_field_for_avg(self):
        runner = AggregateRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "orders", "operation": "avg"},
                input_data={"orders": [{"amount": 5}]},
            )

    def test_aggregate_runner_empty_count_returns_zero(self):
        runner = AggregateRunner()
        result = runner.run(
            config={"input_key": "orders", "operation": "count"},
            input_data={"orders": []},
        )
        self.assertEqual(result, {"result": 0})

    def test_aggregate_runner_empty_min_raises(self):
        runner = AggregateRunner()
        with self.assertRaises(ValueError):
            runner.run(
                config={"input_key": "orders", "field": "amount", "operation": "min"},
                input_data={"orders": []},
            )


if __name__ == "__main__":
    unittest.main()

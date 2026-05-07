import unittest

from app.schemas.workflows import WorkflowDefinition


class WorkflowSchemaTests(unittest.TestCase):
    def test_form_trigger_config_gets_default_fields(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "form_trigger",
                        "label": "Form Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {},
                    }
                ],
                "edges": [],
            }
        )

        self.assertEqual(definition.nodes[0].config["form_title"], "Form Submission")
        self.assertEqual(definition.nodes[0].config["fields"][0]["name"], "email")

    def test_schedule_trigger_config_gets_defaults(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "s1",
                        "type": "schedule_trigger",
                        "label": "Schedule Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {},
                    }
                ],
                "edges": [],
            }
        )

        config = definition.nodes[0].config
        self.assertEqual(config["timezone"], "Asia/Kolkata")
        self.assertTrue(config["enabled"])
        self.assertTrue(isinstance(config.get("rules"), list))
        self.assertEqual(config["rules"][0]["interval"], "hours")
        self.assertEqual(config["rules"][0]["every"], 1)
        self.assertEqual(config["rules"][0]["trigger_minute"], 0)

    def test_loop_control_gets_defaults(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "m1",
                        "type": "manual_trigger",
                        "label": "Manual Trigger",
                        "position": {"x": 0, "y": 0},
                        "config": {},
                    }
                ],
                "edges": [],
            }
        )

        self.assertFalse(definition.loop_control.enabled)
        self.assertEqual(definition.loop_control.max_node_executions, 3)
        self.assertEqual(definition.loop_control.max_total_node_executions, 500)

    def test_merge_config_prunes_mode_irrelevant_keys_for_choose_branch(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "m1",
                        "type": "merge",
                        "label": "Merge",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "mode": "choose_branch",
                            "input_count": 4,
                            "choose_branch": "input3",
                            "output_key": "merged_items",
                            "join_type": "outer",
                            "input_1_field": "email",
                            "input_2_field": "email",
                            "custom_flag": "keep-me",
                        },
                    }
                ],
                "edges": [],
            }
        )

        config = definition.nodes[0].config
        self.assertEqual(config["mode"], "choose_branch")
        self.assertEqual(config["input_count"], 4)
        self.assertEqual(config["choose_branch"], "input3")
        self.assertEqual(config["custom_flag"], "keep-me")
        self.assertNotIn("output_key", config)
        self.assertNotIn("join_type", config)
        self.assertNotIn("input_1_field", config)
        self.assertNotIn("input_2_field", config)

    def test_merge_config_keeps_fields_only_for_combine_by_fields(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "m1",
                        "type": "merge",
                        "label": "Merge",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "mode": "combine_by_fields",
                            "input_1_field": "email",
                            "input_2_field": "profile.email",
                            "join_type": "left",
                            "input_1_handle": "left_in",
                            "input_2_handle": "right_in",
                            "choose_branch": "input2",
                        },
                    }
                ],
                "edges": [],
            }
        )

        config = definition.nodes[0].config
        self.assertEqual(config["mode"], "combine_by_fields")
        self.assertEqual(config["join_type"], "left")
        self.assertEqual(config["input_1_field"], "email")
        self.assertEqual(config["input_2_field"], "profile.email")
        self.assertEqual(config["input_1_handle"], "left_in")
        self.assertEqual(config["input_2_handle"], "right_in")
        self.assertEqual(config["output_key"], "merged")
        self.assertNotIn("choose_branch", config)

    def test_merge_config_prunes_mode_irrelevant_keys_for_append(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "m1",
                        "type": "merge",
                        "label": "Merge",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "mode": "append",
                            "input_count": 5,
                            "output_key": "all_items",
                            "choose_branch": "input4",
                            "join_type": "outer",
                            "input_1_handle": "left_in",
                            "input_2_handle": "right_in",
                            "input_1_field": "email",
                            "input_2_field": "email",
                            "custom_flag": "keep",
                        },
                    }
                ],
                "edges": [],
            }
        )

        config = definition.nodes[0].config
        self.assertEqual(config["mode"], "append")
        self.assertEqual(config["input_count"], 5)
        self.assertEqual(config["output_key"], "all_items")
        self.assertEqual(config["custom_flag"], "keep")
        self.assertNotIn("choose_branch", config)
        self.assertNotIn("join_type", config)
        self.assertNotIn("input_1_handle", config)
        self.assertNotIn("input_2_handle", config)
        self.assertNotIn("input_1_field", config)
        self.assertNotIn("input_2_field", config)

    def test_merge_config_prunes_mode_irrelevant_keys_for_combine_by_position(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "m1",
                        "type": "merge",
                        "label": "Merge",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "mode": "combine_by_position",
                            "join_type": "right",
                            "output_key": "paired",
                            "input_1_handle": "left_side",
                            "input_2_handle": "right_side",
                            "input_1_field": "id",
                            "input_2_field": "id",
                            "choose_branch": "input2",
                        },
                    }
                ],
                "edges": [],
            }
        )

        config = definition.nodes[0].config
        self.assertEqual(config["mode"], "combine_by_position")
        self.assertEqual(config["join_type"], "right")
        self.assertEqual(config["output_key"], "paired")
        self.assertEqual(config["input_1_handle"], "left_side")
        self.assertEqual(config["input_2_handle"], "right_side")
        self.assertNotIn("choose_branch", config)
        self.assertNotIn("input_1_field", config)
        self.assertNotIn("input_2_field", config)

    def test_merge_config_keeps_legacy_fallback_flag_only_when_truthy(self):
        enabled_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "m1",
                        "type": "merge",
                        "label": "Merge",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "mode": "choose_branch",
                            "choose_branch": "input2",
                            "allow_missing_branch_fallback": "yes",
                        },
                    }
                ],
                "edges": [],
            }
        )
        disabled_definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "m1",
                        "type": "merge",
                        "label": "Merge",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "mode": "choose_branch",
                            "choose_branch": "input2",
                            "allow_missing_branch_fallback": False,
                        },
                    }
                ],
                "edges": [],
            }
        )

        enabled_config = enabled_definition.nodes[0].config
        disabled_config = disabled_definition.nodes[0].config
        self.assertTrue(enabled_config.get("allow_missing_branch_fallback"))
        self.assertNotIn("allow_missing_branch_fallback", disabled_config)

    def test_filter_config_normalizes_conditions_and_logic(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "f1",
                        "type": "filter",
                        "label": "Filter",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "input_key": "items",
                            "logic": "OR",
                            "conditions": [
                                {
                                    "field": "amount",
                                    "operator": "greater_than",
                                    "value": "500",
                                },
                                {
                                    "field": "status",
                                    "operator": "contains",
                                    "value_mode": "field",
                                    "value_field": "expected_status",
                                    "case_sensitive": "false",
                                },
                            ],
                        },
                    }
                ],
                "edges": [],
            }
        )

        config = definition.nodes[0].config
        self.assertEqual(config["input_key"], "items")
        self.assertEqual(config["logic"], "or")
        self.assertEqual(len(config["conditions"]), 2)
        self.assertEqual(config["conditions"][0]["join_with_previous"], "and")
        self.assertEqual(config["conditions"][1]["join_with_previous"], "or")
        self.assertEqual(config["conditions"][0]["operator"], "greater_than")
        self.assertEqual(config["conditions"][0]["data_type"], "number")
        self.assertEqual(config["conditions"][1]["value_mode"], "field")
        self.assertEqual(config["conditions"][1]["data_type"], "string")
        self.assertFalse(config["conditions"][1]["case_sensitive"])

    def test_filter_config_migrates_legacy_single_condition(self):
        definition = WorkflowDefinition.model_validate(
            {
                "nodes": [
                    {
                        "id": "f1",
                        "type": "filter",
                        "label": "Filter",
                        "position": {"x": 0, "y": 0},
                        "config": {
                            "input_key": "items",
                            "field": "status",
                            "operator": "equals",
                            "value": "paid",
                        },
                    }
                ],
                "edges": [],
            }
        )

        config = definition.nodes[0].config
        self.assertEqual(config["logic"], "and")
        self.assertEqual(len(config["conditions"]), 1)
        self.assertEqual(config["conditions"][0]["join_with_previous"], "and")
        self.assertEqual(config["conditions"][0]["field"], "status")
        self.assertEqual(config["conditions"][0]["operator"], "equals")
        self.assertEqual(config["conditions"][0]["data_type"], "string")
        self.assertEqual(config["conditions"][0]["value"], "paid")


if __name__ == "__main__":
    unittest.main()

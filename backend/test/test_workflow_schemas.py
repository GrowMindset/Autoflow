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


if __name__ == "__main__":
    unittest.main()

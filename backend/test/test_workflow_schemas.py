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


if __name__ == "__main__":
    unittest.main()

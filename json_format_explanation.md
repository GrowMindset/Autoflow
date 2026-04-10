# Autoflow JSON Format Guide

This document explains the standard JSON schema used by the Autoflow application to store and execute workflows. 

Our format is built around **React Flow**, a widely-used visual node graph library. This makes it incredibly easy to render workflows on the frontend canvas while providing a highly readable, flat structure for the backend execution engine.

---

## High-Level Structure

Every workflow definition is a flat JSON object containing exactly two root-level arrays: `nodes` and `edges`.

```json
{
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

- **`nodes`**: Represents the actual blocks on the canvas (e.g., Triggers, Filters, APIs). It contains the configuration for what the node does.
- **`edges`**: Represents the lines drawn between the blocks. It dictates the direction that data flows during execution.

---

## Deep Dive: The `nodes` Array

Each item in the `nodes` array represents a single executable step.

### Fields Explained:

- **`id`** *(String, Required)*: A globally unique identifier for this specific node block. It often includes the node's type and a timestamp or hash (e.g., `manual_trigger_1775799194946_587`). If a user renames the node, the `id` stays the same. The backend uses this ID to track outputs.
- **`type`** *(String, Required)*: Tells the application *what* this node is. The backend uses this field to load the correct python execution code (e.g., `FilterRunner`), and the frontend uses it to render the correct UI block on the canvas. Examples: `manual_trigger`, `if_else`, `send_gmail_message`.
- **`label`** *(String, Required)*: The human-readable name displayed on the canvas node. 
- **`config`** *(Object, Required)*: The specific settings, options, or inputs for the node. This dictionary varies wildly depending on the node's `type`. For an email node, it configures `to`, `subject`, and `body`. For a manual trigger, it might be `{}` (empty). 
- **`position`** *(Object, Required)*: The exact `x` and `y` coordinates of the node on the frontend canvas. The backend engine ignores this, but it is strictly necessary for the React Flow frontend to render the node in the correct place.

### Node Example:
```json
{
  "id": "send_gmail_message_1775799383986_868",
  "type": "send_gmail_message",
  "label": "Send Gmail Message",
  "config": {
    "to": "officeworkintern@gmail.com",
    "subject": "System Alert",
    "body": "User {{$json.name}} has been registered."
  },
  "position": {
    "x": 747.56,
    "y": -263.55
  }
}
```

---

## Deep Dive: The `edges` Array

Each item in the `edges` array represents a relationship or "data pipeline" from one node to another. 

### Fields Explained:

- **`id`** *(String, Required)*: A unique identifier for the connection line itself. Typically formatted like `e_{source_id}_{target_id}`.
- **`source`** *(String, Required)*: The `id` of the node where the data is *coming from*.
- **`target`** *(String, Required)*: The `id` of the node where the data is *going to*.
- **`branch`** *(String | null)*: Used to explicitly dictate routing behavior. If an edge comes out of the "true" side of an `if_else` node, this field might say `"true"`. The backend engine explicitly looks at this field when generating paths. For standard linear nodes without branches, this is `null`.
- **`sourceHandle` / `targetHandle`** *(String | null)*: Mostly utilized by the Frontend React Flow UI to know exactly *which* dot (handle) on the UI block the edge connection line is physically attached to. For branching nodes, the `sourceHandle` typically matches the logical `branch` value.

### Edge Example:
```json
{
  "id": "e_if_else_1775799319490_361_send_gmail_message_1775799383986_868_true",
  "source": "if_else_1775799319490_361",
  "target": "send_gmail_message_1775799383986_868",
  "branch": null,
  "sourceHandle": "true",
  "targetHandle": null
}
```
*(In this example, data flows from the `if_else` node into the `send_gmail_message` node, specifically originating from the "true" output port of the `if_else` node.)*

---

## Full Reference Example 

Here is a simple, complete workflow where a user submits a form. If they input the name "Anokhi", they are sent a welcome email. If their name is something else, they are added to a Google Sheet.

```json
{
  "nodes": [
    {
      "id": "form_trigger_1",
      "type": "form_trigger",
      "label": "New User Form",
      "config": {
        "fields": [{ "name": "email", "type": "email", "required": true }]
      },
      "position": { "x": 100, "y": 100 }
    },
    {
      "id": "if_else_node_1",
      "type": "if_else",
      "label": "Is Anokhi?",
      "config": {
        "field": "name",
        "value": "Anokhi",
        "operator": "equals"
      },
      "position": { "x": 300, "y": 100 }
    },
    {
      "id": "email_node_1",
      "type": "send_gmail_message",
      "label": "Send Welcome Email",
      "config": {
        "to": "{{$json.email}}",
        "subject": "Hello Anokhi",
        "body": "Welcome to the system!"
      },
      "position": { "x": 500, "y": 0 }
    },
    {
      "id": "sheets_node_1",
      "type": "search_update_google_sheets",
      "label": "Save to Sheets",
      "config": {
        "sheet_name": "Sheet1",
        "spreadsheet_id": "1234abc"
      },
      "position": { "x": 500, "y": 200 }
    }
  ],
  "edges": [
    {
      "id": "edge_form_to_if",
      "source": "form_trigger_1",
      "target": "if_else_node_1",
      "sourceHandle": null,
      "targetHandle": null
    },
    {
      "id": "edge_if_to_email",
      "source": "if_else_node_1",
      "target": "email_node_1",
      "sourceHandle": "true",
      "targetHandle": null
    },
    {
      "id": "edge_if_to_sheets",
      "source": "if_else_node_1",
      "target": "sheets_node_1",
      "sourceHandle": "false",
      "targetHandle": null
    }
  ]
}
```

### Understanding the Execution Flow
Here is exactly how our backend interprets the JSON above:
1. The **Backend** receives the JSON and loops through the `nodes` array to map the configurations by `id`.
2. It loops through the `edges` array and builds a directed graph diagram. It calculates that `form_trigger_1` is the starting point because no edges' `target` values point to it.
3. The `DagExecutor` executes `form_trigger_1`.
4. It passes the resulting data output to the `if_else_node_1` (explicitly directed by `edge_form_to_if` referencing the IDs).
5. When `if_else_node_1` evaluates the config comparing the name, it outputs an internal decision indicator (e.g. `_branch: "true"` or `_branch: "false"`). 
6. Based on the decision, the backend routes to the correct node explicitly matching the respective `sourceHandle` strings. It executes the email node or the sheets node!

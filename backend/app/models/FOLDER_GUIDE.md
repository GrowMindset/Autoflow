# Database Schema & Node Config Reference
# Workflow Automation Platform

> **Owner:** Ishika  
> **Last updated:** April 2026  
> **Version:** 2.0  
> **Status:** ✅ Locked — agreed by full team

---

## Table of Contents

1. [Overview](#overview)
2. [Design Decisions](#design-decisions)
3. [Tables](#tables)
   - [users](#1-users)
   - [workflows](#2-workflows)
   - [executions](#3-executions)
   - [node_executions](#4-node_executions)
   - [app_credentials](#5-app_credentials)
   - [webhook_endpoints](#6-webhook_endpoints)
4. [Relationships](#relationships)
5. [Workflow Definition JSON Structure](#workflow-definition-json-structure)
6. [Node Config Reference](#node-config-reference)
   - [filter](#1-filter)
   - [if_else](#2-if_else)
   - [switch](#3-switch)
   - [merge](#4-merge)
   - [aggregate](#5-aggregate)
   - [datetime_format](#6-datetime_format)
   - [split_in](#7-split_in)
   - [split_out](#8-split_out)
7. [Status Values Reference](#status-values-reference)
8. [Important Rules — Read Before Writing Code](#important-rules--read-before-writing-code)

---

## Overview

This document is the **single source of truth** for the database schema and node config contracts of the Workflow Automation Platform.

**Every team member must read this before writing any model, migration, query, node runner, or config panel form.**

### Tech

- **Database:** PostgreSQL 15
- **ORM:** SQLAlchemy (async)
- **Migrations:** Alembic
- **Primary Keys:** UUID everywhere (`gen_random_uuid()`)
- **Timestamps:** `TIMESTAMPTZ` everywhere (timezone-aware)

### 6 Tables at a Glance

| Table | Purpose | Phase |
|---|---|---|
| `users` | User accounts and authentication | Phase 1 |
| `workflows` | Workflow definitions (nodes + edges as JSONB) | Phase 1 |
| `executions` | One row per workflow run | Phase 1 |
| `node_executions` | One row per node per run | Phase 1 |
| `app_credentials` | OAuth tokens and API keys for third-party apps | Phase 3 (create now, use later) |
| `webhook_endpoints` | Registered public URLs for webhook trigger nodes | Phase 1 |

---

## Design Decisions

These are team-agreed decisions. Do not change them without discussing with the full team.

### ✅ UUID primary keys everywhere
Integer IDs expose resource counts and allow enumeration attacks (changing `/workflows/1` to `/workflows/2`). UUIDs prevent this completely.

### ✅ No multi-tenancy (no tenant_id)
User separation is enforced purely via `user_id` FK on every table. Every query that fetches data must filter by `user_id` from the JWT. Sufficient for prototype.

### ✅ Workflow canvas stored as JSONB (not a separate nodes table)
The entire canvas — all nodes, edges, positions, configs — lives in a single `definition` JSONB column on the `workflows` table. Avoids complex joins, easier to update, same approach as n8n.

### ✅ Executions are never overwritten
Every run creates a new row in `executions` and N new rows in `node_executions`. History is preserved. A cleanup rule (keep last 50 per workflow) will be added in Phase 3 when it matters.

### ✅ Both input_data and output_data stored per node
Powers the frontend side panel (click a node → see what went in and came out). Essential for debugging failures.

### ✅ Error messages stored in DB
The Celery worker is a separate process — it cannot talk directly to the frontend. DB is the only shared communication layer between Celery and FastAPI. Error messages must be written to DB so the frontend can display them. Redis pub/sub is used for real-time delivery to online users — DB is the persistent fallback for users who were offline.

### ✅ is_published instead of is_active on workflows
`is_published` maps directly to a real product concept — a workflow is either a draft (false) or live and triggerable (true). More meaningful than a generic active/inactive flag.

---

## Tables

---

### 1. `users`

Stores all registered user accounts. Every other table references this via `user_id`.

```sql
CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email            VARCHAR(255) NOT NULL UNIQUE,
    username         VARCHAR(100) NOT NULL UNIQUE,
    hashed_password  TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### Columns

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key. Auto-generated on insert. |
| `email` | VARCHAR(255) | NO | — | Login identifier. Unique across all users. |
| `username` | VARCHAR(100) | NO | — | Display name shown in UI. Unique across all users. |
| `hashed_password` | TEXT | NO | — | bcrypt hash of the password. **Never store plain text.** |
| `created_at` | TIMESTAMPTZ | NO | `now()` | When the account was created. |

#### Notes
- No `is_active` — account deactivation is out of scope for prototype.
- No `updated_at` — user profile editing is out of scope for prototype.
- `email` is the login identity. `username` is the display identity. Both unique.

---

### 2. `workflows`

Each row represents one workflow belonging to a user. The full canvas (nodes, edges, positions, configs) is stored as JSONB in `definition`.

```sql
CREATE TABLE workflows (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          VARCHAR(100) NOT NULL,
    description   TEXT,
    definition    JSONB NOT NULL DEFAULT '{"nodes": [], "edges": []}',
    is_published  BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### Columns

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key. |
| `user_id` | UUID | NO | — | FK → `users`. Owner of this workflow. All queries filter by this. |
| `name` | VARCHAR(100) | NO | — | Human-readable name shown in the workflow list UI. |
| `description` | TEXT | YES | NULL | Optional description of what this workflow does. |
| `definition` | JSONB | NO | `{"nodes":[],"edges":[]}` | The entire canvas. See [Workflow Definition JSON Structure](#workflow-definition-json-structure). |
| `is_published` | BOOLEAN | NO | `false` | `true` = live, can be triggered. `false` = draft, cannot be triggered. |
| `created_at` | TIMESTAMPTZ | NO | `now()` | When the workflow was first saved. |
| `updated_at` | TIMESTAMPTZ | NO | `now()` | Updated on every save. Used for "sort by recently edited". |

#### Notes
- `is_published` defaults to `false` — every new workflow starts as a draft.
- `updated_at` must be updated on every `PUT /workflows/{id}`. Use SQLAlchemy `onupdate` or update manually in the service layer.
- When `is_published` is set to `false`, `webhook_endpoints.is_active` must also be set to `false` for all webhooks belonging to this workflow. Handled in `WorkflowService`, not at DB level.
- `ON DELETE CASCADE` on `user_id` — deleting a user removes all their workflows.

---

### 3. `executions`

One row per workflow run. Created the moment a user clicks Run, a webhook fires, or a form is submitted.

```sql
CREATE TABLE executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    triggered_by    VARCHAR(50) NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error_message   TEXT
);
```

#### Columns

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key. Frontend polls `GET /executions/{id}` using this. |
| `workflow_id` | UUID | NO | — | FK → `workflows`. Which workflow was run. |
| `user_id` | UUID | NO | — | FK → `users`. Who triggered the run. For filtering execution history. |
| `status` | VARCHAR(20) | NO | `'PENDING'` | Current state. See [Status Values](#status-values-reference). |
| `triggered_by` | VARCHAR(50) | NO | — | What started this run. Examples: `manual`, `webhook`, `form`, `schedule`, or a node type for single-node tests. |
| `started_at` | TIMESTAMPTZ | YES | NULL | Set when Celery worker starts executing. Null while queued. |
| `finished_at` | TIMESTAMPTZ | YES | NULL | Set when execution completes. Null while running. Frontend stops polling when this is set. |
| `error_message` | TEXT | YES | NULL | If the whole execution crashes before nodes run, reason stored here. |

#### Notes
- `started_at` is NULL when status is `PENDING` — job is in Redis queue but not picked up yet.
- `finished_at` is NULL while status is `RUNNING`. Frontend uses this to decide whether to keep polling.
- `error_message` here is for **execution-level** failures. Node-level errors go in `node_executions.error_message`.
- Rows are **never updated after SUCCEEDED/FAILED** — executions are immutable history.

---

### 4. `node_executions`

One row per node per workflow run. 5 nodes × 1 run = 5 rows here, all linked to 1 row in `executions`.

This table powers the frontend canvas colouring (green/red per node) and the per-node input/output side panel.

```sql
CREATE TABLE node_executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    node_id         VARCHAR(50) NOT NULL,
    node_type       VARCHAR(50) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    input_data      JSONB,
    output_data     JSONB,
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);
```

#### Columns

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key. |
| `execution_id` | UUID | NO | — | FK → `executions`. Groups all node results for one run. |
| `node_id` | VARCHAR(50) | NO | — | The node's `id` from `definition` JSONB — e.g. `"n1"`, `"n2"`. **Bridge between canvas and execution results.** |
| `node_type` | VARCHAR(50) | NO | — | e.g. `"if_else"`, `"filter"`. Stored here so logs are readable without joining `workflows`. |
| `status` | VARCHAR(20) | NO | `'PENDING'` | Same 4 states as `executions`. |
| `input_data` | JSONB | YES | NULL | JSON this node received. Null for trigger nodes. |
| `output_data` | JSONB | YES | NULL | JSON this node produced. Null if node failed before producing output. |
| `error_message` | TEXT | YES | NULL | If this specific node failed, the reason. Null if succeeded. |
| `started_at` | TIMESTAMPTZ | YES | NULL | When this node started executing. |
| `finished_at` | TIMESTAMPTZ | YES | NULL | When this node finished. `finished_at - started_at` = node execution duration. |

#### Notes
- `node_id` must match exactly with `workflows.definition.nodes[*].id`. Anil uses this to map results back to canvas nodes and colour them.
- Nodes that were never reached (e.g. after a failure) stay with `status = 'PENDING'` and all nullable fields as NULL.
- Always populate `input_data` and `output_data` — they power the frontend debug panel.

#### Real Example

Workflow with 4 nodes, one run — `n3` fails, `n4` never reached:

| node_id | node_type | status | input_data | output_data | error_message |
|---|---|---|---|---|---|
| n1 | manual_trigger | SUCCEEDED | NULL | `{"triggered": true}` | NULL |
| n2 | filter | SUCCEEDED | `{"items": [...]}` | `{"items": [2 matched]}` | NULL |
| n3 | if_else | FAILED | `{"items": [...]}` | NULL | `"field 'status' not found in input"` |
| n4 | aggregate | PENDING | NULL | NULL | NULL |

---

### 5. `app_credentials`

Stores OAuth tokens and API keys for third-party app integrations per user.

> ⚠️ **Phase 3 only.** Create this table now in migrations so it exists, but no service logic reads or writes to it until Phase 3.

```sql
CREATE TABLE app_credentials (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app_name    VARCHAR(50) NOT NULL,
    token_data  JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### Columns

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key. Referenced by action nodes in workflow definition. |
| `user_id` | UUID | NO | — | FK → `users`. Credentials are strictly per-user. |
| `app_name` | VARCHAR(50) | NO | — | Which app. One of: `gmail`, `sheets`, `telegram`, `whatsapp`, `linkedin`. |
| `token_data` | JSONB | NO | — | The actual tokens. Shape varies per app — see below. |
| `created_at` | TIMESTAMPTZ | NO | `now()` | When the credential was connected. |

#### token_data Shape Per App

```json
// Gmail & Google Sheets (shared OAuth app)
{ "access_token": "ya29...", "refresh_token": "1//...", "expires_at": "2026-04-07T10:00:00Z" }

// Telegram
{ "bot_token": "123456:ABC-..." }

// WhatsApp Business
{ "access_token": "EAAb...", "phone_number_id": "123456789" }

// LinkedIn
{ "access_token": "AQX...", "expires_at": "2026-07-01T00:00:00Z" }
```

#### Notes
- JSONB because different apps need different token fields — one flexible column handles all.
- In Phase 3, action nodes store `credential_id` in their config, never the raw token.
- Tokens stored as plain text for prototype. Encryption can be added in a future version.

---

### 6. `webhook_endpoints`

Registers a unique public URL for each webhook trigger node. When an external service POSTs to that URL, the backend looks up the workflow and enqueues an execution.

```sql
CREATE TABLE webhook_endpoints (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id  UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    node_id      VARCHAR(50) NOT NULL,
    path_token   VARCHAR(100) NOT NULL UNIQUE,
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### Columns

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key. |
| `workflow_id` | UUID | NO | — | FK → `workflows`. Which workflow to trigger on incoming POST. |
| `user_id` | UUID | NO | — | FK → `users`. Owner. For authorization checks. |
| `node_id` | VARCHAR(50) | NO | — | Which node in the workflow is the webhook trigger — e.g. `"n1"`. |
| `path_token` | VARCHAR(100) | NO | — | Random token in the public URL. **Globally unique. Never changes after creation.** |
| `is_active` | BOOLEAN | NO | `true` | If `false`, incoming POSTs return 404. Linked to `workflows.is_published`. |
| `created_at` | TIMESTAMPTZ | NO | `now()` | When the webhook was registered. |

#### Notes
- `path_token` generated via `secrets.token_urlsafe(16)` when a workflow with a Webhook Trigger node is saved for the first time.
- Full public URL: `POST /webhook/{path_token}`
- Anil displays this URL in the Webhook node config panel for the user to copy.
- `is_active` must flip to `false` automatically when `workflows.is_published` is set to `false`. Handled in `WorkflowService`.
- `path_token` is **immutable** after creation — external services register this URL and changing it breaks their integration.
- `ON DELETE CASCADE` on `workflow_id` — deleting a workflow removes its webhook registrations.

---

## Relationships

```
users
 ├── workflows           (user_id → users.id)
 │    ├── executions          (workflow_id → workflows.id)
 │    │    └── node_executions    (execution_id → executions.id)
 │    └── webhook_endpoints   (workflow_id → workflows.id)
 ├── executions          (user_id → users.id)
 ├── app_credentials     (user_id → users.id)
 └── webhook_endpoints   (user_id → users.id)
```

**All foreign keys use `ON DELETE CASCADE`** — deleting a user removes all their data. Deleting a workflow removes all its executions, node executions, and webhook registrations.

---

## Workflow Definition JSON Structure

The `workflows.definition` JSONB column stores the full canvas. This is the **contract between backend DAG executor and frontend React Flow** — both sides must read and write this exact shape.

```json
{
  "nodes": [
    {
      "id": "n1",
      "type": "manual_trigger",
      "label": "Start",
      "position": { "x": 100, "y": 150 },
      "config": {}
    },
    {
      "id": "n2",
      "type": "if_else",
      "label": "Check Status",
      "position": { "x": 350, "y": 150 },
      "config": {
        "field": "status",
        "operator": "equals",
        "value": "paid"
      }
    },
    {
      "id": "n3",
      "type": "filter",
      "label": "Filter Orders",
      "position": { "x": 600, "y": 100 },
      "config": {
        "input_key": "items",
        "field": "amount",
        "operator": "greater_than",
        "value": "500"
      }
    }
  ],
  "edges": [
    { "id": "e1", "source": "n1", "target": "n2" },
    { "id": "e2", "source": "n2", "target": "n3", "branch": "true" }
  ]
}
```

### Node Object Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | YES | Unique within this workflow. e.g. `"n1"`, `"n2"`. **Frontend generates this.** Must exactly match `node_executions.node_id`. |
| `type` | string | YES | Node type key. Determines which runner the DAG executor calls. See full list below. |
| `label` | string | YES | Human-readable name on the canvas. Backend never reads this. |
| `position` | object | YES | `{ "x": number, "y": number }`. Canvas coordinates for React Flow. Backend never reads this. |
| `config` | object | YES | Node-specific settings. Shape varies by type. Can be `{}` for nodes with no config. See [Node Config Reference](#node-config-reference). |

### Edge Object Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | YES | Unique within this workflow. e.g. `"e1"`. |
| `source` | string | YES | `id` of the source node. |
| `target` | string | YES | `id` of the target node. |
| `branch` | string | NO | **Only for `if_else` and `switch` nodes.** Value is `"true"` / `"false"` for if_else, or a case label for switch. |

### All Node Type Keys

#### Trigger Nodes
| type key | Phase | Status |
|---|---|---|
| `manual_trigger` | Phase 1 | ✅ Live |
| `form_trigger` | Phase 1 | ✅ Live |
| `webhook_trigger` | Phase 1 | ✅ Live |
| `workflow_trigger` | Future | 🔘 Dummy — UI placeholder only |

#### Action Nodes
| type key | Phase | Status |
|---|---|---|
| `get_gmail_message` | Phase 3 | 🔘 Dummy until Phase 3 |
| `send_gmail_message` | Phase 3 | 🔘 Dummy until Phase 3 |
| `create_google_sheets` | Phase 3 | 🔘 Dummy until Phase 3 |
| `search_update_google_sheets` | Phase 3 | 🔘 Dummy until Phase 3 |
| `telegram` | Phase 3 | 🔘 Dummy until Phase 3 |
| `whatsapp` | Phase 3 | 🔘 Dummy until Phase 3 |
| `linkedin` | Phase 3 | 🔘 Dummy until Phase 3 |

#### Data Transformation Nodes
| type key | Phase | Status |
|---|---|---|
| `filter` | Phase 1 | ✅ Live |
| `if_else` | Phase 1 | ✅ Live |
| `switch` | Phase 1 | ✅ Live |
| `merge` | Phase 1 | ✅ Live |
| `aggregate` | Phase 1 | ✅ Live |
| `datetime_format` | Phase 1 | ✅ Live |
| `split_in` | Phase 1 | ✅ Live |
| `split_out` | Phase 1 | ✅ Live |

#### AI Node
| type key | Phase | Status |
|---|---|---|
| `ai_agent` | Phase 2 | ✅ Live — Phase 2 |

---

## Node Config Reference

This section defines the exact `config` object shape for every live transformation node.

> **This is the hard contract between Ishika (node runners) and Anil (config panel forms).** Both sides must use these exact field names — no exceptions. A mismatch is a silent bug that only shows up at runtime.

### Shared Operators

Used by `filter`, `if_else`, and `switch`. Anil renders these as a dropdown.

| operator value | behaviour |
|---|---|
| `equals` | field == value |
| `not_equals` | field != value |
| `greater_than` | field > value (numeric) |
| `less_than` | field < value (numeric) |
| `contains` | value is substring of field (string) |
| `not_contains` | value is not substring of field (string) |

> `value` is always stored as a **string** in config. Runner casts to number automatically when operator is `greater_than` or `less_than`.

---

### 1. `filter`

Takes an array and returns only items matching the condition.

| config field | type | required | default | description |
|---|---|---|---|---|
| `input_key` | string | YES | — | Key in `input_data` holding the array. e.g. `"items"`, `"orders"`. |
| `field` | string | YES | — | Field inside each array item to evaluate. e.g. `"amount"`, `"status"`. |
| `operator` | string | YES | — | One of the 6 shared operators. |
| `value` | string | YES | — | Value to compare against. Always string — runner casts if needed. |

```json
// Config
{ "input_key": "items", "field": "amount", "operator": "greater_than", "value": "500" }

// Input → Output
IN:  { "items": [{"amount": 300}, {"amount": 700}, {"amount": 150}] }
OUT: { "items": [{"amount": 700}] }
```

> Output key is always the same as `input_key`. Filtered array replaces original.

---

### 2. `if_else`

Evaluates one condition and routes to `true` or `false` branch.

| config field | type | required | default | description |
|---|---|---|---|---|
| `field` | string | YES | — | Key in `input_data` to evaluate. e.g. `"status"`. |
| `operator` | string | YES | — | One of the 6 shared operators. |
| `value` | string | YES | — | Value to compare against. |

```json
// Config
{ "field": "status", "operator": "equals", "value": "paid" }

// Input → Output
IN:  { "status": "paid", "amount": 500 }
OUT: { "status": "paid", "amount": 500, "_branch": "true" }

// Edges in definition
{ "id": "e1", "source": "n2", "target": "n3", "branch": "true"  }
{ "id": "e2", "source": "n2", "target": "n4", "branch": "false" }
```

> `_branch` is internal — DAG executor reads it to follow the correct edge, then strips it before passing data to the next node.

---

### 3. `switch`

Evaluates multiple conditions on one field, routes to the first matching branch.

| config field | type | required | default | description |
|---|---|---|---|---|
| `field` | string | YES | — | Key in `input_data` to evaluate for all cases. |
| `cases` | array | YES | — | List of `{ label, operator, value }` objects. Evaluated top to bottom — first match wins. |
| `default_case` | string | NO | `"default"` | Branch label when no case matches. |

```json
// Config
{
  "field": "country",
  "cases": [
    { "label": "india", "operator": "equals", "value": "IN" },
    { "label": "usa",   "operator": "equals", "value": "US" }
  ],
  "default_case": "default"
}

// Input → Output
IN:  { "country": "US" }
OUT: { "country": "US", "_branch": "usa" }

IN:  { "country": "JP" }
OUT: { "country": "JP", "_branch": "default" }

// Edges in definition
{ "id": "e1", "source": "n2", "target": "n3", "branch": "india"   }
{ "id": "e2", "source": "n2", "target": "n4", "branch": "usa"     }
{ "id": "e3", "source": "n2", "target": "n5", "branch": "default" }
```

> `case.label` must exactly match the `branch` field on edges. Anil uses labels as output handle names on the switch node in React Flow.

---

### 4. `merge`

Collects outputs from multiple incoming branches into one array.

| config field | type | required | default | description |
|---|---|---|---|---|
| — | — | — | — | No config fields needed. Leave as `{}`. |

```json
// Config
{}

// Input → Output (append mode — always)
Branch 1: { "country": "IN", "tax": 18 }
Branch 2: { "country": "US", "tax": 10 }

OUT: { "merged": [
  { "country": "IN", "tax": 18 },
  { "country": "US", "tax": 10 }
]}
```

> Anil does not need to build a config panel for this node. No settings at all.

---

### 5. `aggregate`

Performs a mathematical operation across all items in an array.

| config field | type | required | default | description |
|---|---|---|---|---|
| `input_key` | string | YES | — | Key in `input_data` holding the array. |
| `field` | string | NO* | — | Field inside each item to operate on. *Required for all operations except `count`. |
| `operation` | string | YES | — | One of: `sum`, `count`, `min`, `max`, `avg`. |
| `output_key` | string | NO | `"result"` | Key name for result in `output_data`. |

| operation | needs field | example |
|---|---|---|
| `sum` | YES | `[300, 700, 150]` → `1150` |
| `count` | NO | `[3 items]` → `3` |
| `min` | YES | `[300, 700, 150]` → `150` |
| `max` | YES | `[300, 700, 150]` → `700` |
| `avg` | YES | `[300, 700, 150]` → `383.33` |

```json
// Config — sum
{ "input_key": "items", "field": "amount", "operation": "sum", "output_key": "total_revenue" }

// Input → Output
IN:  { "items": [{"amount": 300}, {"amount": 700}, {"amount": 150}] }
OUT: { "total_revenue": 1150 }

// Config — count (no field needed)
{ "input_key": "orders", "operation": "count" }

IN:  { "orders": [{"id": 1}, {"id": 2}, {"id": 3}] }
OUT: { "result": 3 }
```

> Runner must throw a clear error if `field` is missing for `sum`, `min`, `max`, or `avg`.

---

### 6. `datetime_format`

Parses a date string and reformats it into a target format.

| config field | type | required | default | description |
|---|---|---|---|---|
| `field` | string | YES | — | Key in `input_data` holding the date string. e.g. `"order_date"`. |
| `output_format` | string | YES | — | Target format using Python `strftime` tokens. |

```json
// Config
{ "field": "order_date", "output_format": "%d %B %Y" }

// Input → Output
IN:  { "order_date": "2026-04-07", "amount": 500 }
OUT: { "order_date": "07 April 2026", "amount": 500 }
```

**Common output_format values — Anil shows these as quick-select options:**

| output_format | example output | use case |
|---|---|---|
| `%Y-%m-%d` | `2026-04-07` | ISO standard, Google Sheets |
| `%d/%m/%Y` | `07/04/2026` | Indian / European format |
| `%d %B %Y` | `07 April 2026` | Human-readable, emails |
| `%I:%M %p` | `10:30 AM` | Time only, 12hr |
| `%d %b %Y %H:%M` | `07 Apr 2026 14:30` | Full datetime, logs |

> Input format auto-detected via `python-dateutil` — no `input_format` config field. Output overwrites the same `field` key.
> **Runner:** `from dateutil import parser` → `parser.parse(value)` → `.strftime(output_format)`

---

### 7. `split_in`

Takes an array and emits each item individually to all downstream nodes. Always paired with `split_out`.

| config field | type | required | default | description |
|---|---|---|---|---|
| `input_key` | string | YES | — | Key in `input_data` holding the array to split. e.g. `"tickets"`. |

```json
// Config
{ "input_key": "tickets" }

// Input → What each downstream node receives per iteration
IN: { "tickets": [{"id": 1, "msg": "help"}, {"id": 2, "msg": "bug"}] }

Iteration 1: { "item": {"id": 1, "msg": "help"}, "_split_index": 0 }
Iteration 2: { "item": {"id": 2, "msg": "bug"},  "_split_index": 1 }
```

> `_split_index` is internal — used by `split_out` to reassemble results in original order.
> The complexity of `split_in` lives entirely in the DAG executor, not in the runner config.

**DAG executor behaviour:**
1. Reads `input_key`, extracts the array
2. Loops through each item — runs all downstream nodes once per item
3. Stores each iteration's output tagged with `_split_index`
4. Stops looping when it reaches `split_out`

---

### 8. `split_out`

Collects all per-item outputs from a `split_in` loop and reassembles them into one array.

| config field | type | required | default | description |
|---|---|---|---|---|
| `output_key` | string | NO | `"results"` | Key name for the collected array in `output_data`. |

```json
// Config
{ "output_key": "processed_tickets" }

// or simply: {}

// Output
{ "processed_tickets": [
  { "id": 1, "reply": "Hi, we can help..." },
  { "id": 2, "reply": "We found the bug..." }
]}
```

> `split_out` sorts by `_split_index` and strips it before assembling the final array. Downstream nodes never see `_split_index`.

---

## Status Values Reference

Both `executions.status` and `node_executions.status` use the same 4 values:

| Value | Meaning |
|---|---|
| `PENDING` | Created — waiting to be picked up by Celery worker |
| `RUNNING` | Currently executing |
| `SUCCEEDED` | Completed without error |
| `FAILED` | Encountered an error |

### Valid Transitions

```
PENDING → RUNNING → SUCCEEDED
                 → FAILED
```

No other transitions are valid. A `SUCCEEDED` or `FAILED` row is **never updated again**.

---

## Important Rules — Read Before Writing Code

> Non-negotiable. Every team member must follow these.

### 1. Always filter by user_id
Every query that returns data must include `WHERE user_id = :current_user_id`. Never return data without this filter.

```python
# ✅ Correct
db.query(Workflow).filter(Workflow.user_id == current_user.id)

# ❌ Wrong — returns all users' workflows
db.query(Workflow).all()
```

### 2. Never expose hashed_password in API responses
Use a separate Pydantic response schema that excludes `hashed_password`. It must never appear in any response under any circumstance.

### 3. node_id in node_executions must match definition exactly
When the DAG executor writes `node_executions` rows, `node_id` must be copied exactly from `workflow.definition.nodes[*].id`. Anil depends on this exact match to colour canvas nodes.

### 4. updated_at on workflows must always be refreshed
Every `PUT /workflows/{id}` must update `updated_at` to `now()`. Do not forget — it powers "sort by recently edited".

### 5. webhook path_token is immutable
Once created, `path_token` must never change. External services register this URL — changing it silently breaks their integration.

### 6. config field names are a hard contract
Node runner reads and config panel form writes must use **identical field names**. If the runner reads `config["input_key"]` and the form writes `config["inputKey"]` — the runner gets `None` and fails silently. When in doubt, re-read this document.

### 7. app_credentials — do not implement in Phase 1 or 2
The table exists. Do not write any service logic, routes, or runners that read from it until Phase 3 starts.

### 8. Dummy nodes must not crash the executor
All Phase 3 action nodes must have a dummy runner that logs `"Node skipped — integration pending"` and passes `input_data` through as `output_data` unchanged. The workflow must complete with `SUCCEEDED` even if it contains dummy nodes.

---

*This document is maintained by Ishika. Any schema or config change must be discussed with the full team and this file updated before any code is written.*

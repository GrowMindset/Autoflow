# Database Schema — Workflow Automation Platform

> **Owner:** Ishika Gadhwal  
> **Last updated:** April 2026  
> **Version:** 1.0  
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
6. [Status Values Reference](#status-values-reference)
7. [Important Rules — Read Before Writing Code](#important-rules--read-before-writing-code)

---

## Overview

This document is the **single source of truth** for the database schema of the Workflow Automation Platform. Every table, every column, and every design decision is documented here.

**Before writing any model, migration, or query — read this file completely.**

### Tech

- **Database:** PostgreSQL 15
- **ORM:** SQLAlchemy (async)
- **Migrations:** Alembic
- **Primary Keys:** UUID everywhere (generated via `gen_random_uuid()`)
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
Integer IDs expose resource counts and allow enumeration attacks (changing `/workflows/1` to `/workflows/2`). UUIDs prevent this.

### ✅ No multi-tenancy (no tenant_id)
User separation is enforced purely via `user_id` FK on every table. Every query that fetches data must filter by `user_id` from the JWT. This is sufficient for a prototype.

### ✅ Workflow canvas stored as JSONB (not separate nodes table)
The entire canvas — all nodes, edges, positions, and configs — lives in a single `definition` JSONB column on the `workflows` table. This avoids complex joins, is easier to update, and is the same approach used by n8n.

### ✅ Executions are never overwritten
Every run creates a new row in `executions` and N new rows in `node_executions`. History is preserved. A cleanup rule (keep last 50 per workflow) will be added in Phase 3.

### ✅ Both input_data and output_data stored per node
This is what powers the frontend side panel (click a node → see what went in and what came out). It is also essential for debugging failures.

### ✅ Error messages stored in DB (not just logs)
The Celery worker is a separate process — it cannot talk directly to the frontend. The DB is the only shared communication layer between Celery and FastAPI. Error messages must be written to the DB so the frontend can display them to the user.

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
| `email` | VARCHAR(255) | NO | — | Login identifier. Must be unique across all users. |
| `username` | VARCHAR(100) | NO | — | Display name shown in the UI. Must be unique. |
| `hashed_password` | TEXT | NO | — | bcrypt hash of the user's password. **Never store plain text.** |
| `created_at` | TIMESTAMPTZ | NO | `now()` | Timestamp when the account was created. |

#### Notes
- No `is_active` — account deactivation is out of scope for prototype.
- No `updated_at` — user profile editing is out of scope for prototype.
- `email` is the login identity. `username` is the display identity. Both unique.

---

### 2. `workflows`

Each row represents one workflow belonging to a user. The full canvas definition (all nodes, edges, positions, configs) is stored as JSONB in the `definition` column.

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
| `user_id` | UUID | NO | — | FK to `users`. Owner of this workflow. Used to filter — users only see their own. |
| `name` | VARCHAR(100) | NO | — | Human-readable name shown in the workflow list UI. |
| `description` | TEXT | YES | NULL | Optional description of what this workflow does. |
| `definition` | JSONB | NO | `{"nodes":[],"edges":[]}` | The entire canvas — nodes, edges, positions, configs. See structure below. |
| `is_published` | BOOLEAN | NO | `false` | `true` = workflow is live and can be triggered. `false` = draft, cannot be triggered. |
| `created_at` | TIMESTAMPTZ | NO | `now()` | When the workflow was first saved. |
| `updated_at` | TIMESTAMPTZ | NO | `now()` | Updated every time the workflow is saved. Used for "sort by recently edited". |

#### Notes
- `is_published` defaults to `false` — a new workflow starts as a draft.
- `updated_at` must be updated on every PUT /workflows/{id} call. Use a SQLAlchemy `onupdate` trigger or update it manually in the service layer.
- `ON DELETE CASCADE` on `user_id` — deleting a user deletes all their workflows.
- See [Workflow Definition JSON Structure](#workflow-definition-json-structure) for the exact shape of `definition`.

---

### 3. `executions`

One row per workflow run. Created when a user clicks Run, a webhook fires, or a form is submitted.

```sql
CREATE TABLE executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    triggered_by    VARCHAR(20) NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error_message   TEXT
);
```

#### Columns

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key. The frontend polls `GET /executions/{id}` using this. |
| `workflow_id` | UUID | NO | — | FK to `workflows`. Which workflow was run. |
| `user_id` | UUID | NO | — | FK to `users`. Who triggered the run. For filtering execution history. |
| `status` | VARCHAR(20) | NO | `'PENDING'` | Current state. See [Status Values](#status-values-reference). |
| `triggered_by` | VARCHAR(20) | NO | — | What started the run. One of: `manual`, `webhook`, `form`. |
| `started_at` | TIMESTAMPTZ | YES | NULL | Set when Celery worker starts executing. Null while queued. |
| `finished_at` | TIMESTAMPTZ | YES | NULL | Set when execution completes (success or failure). Null while running. |
| `error_message` | TEXT | YES | NULL | If the whole execution crashes before nodes run, reason stored here. |

#### Notes
- `started_at` is NULL when status is `PENDING` (job is in Redis queue but not picked up yet).
- `finished_at` is NULL while status is `RUNNING`. Frontend uses this to decide whether to keep polling.
- `error_message` here is for **execution-level** failures (e.g. Celery task crash). Node-level errors go in `node_executions.error_message`.
- Row is **never updated after SUCCEEDED/FAILED** — executions are immutable history.

---

### 4. `node_executions`

One row per node per workflow run. If a workflow has 5 nodes and runs once, this table gets 5 new rows — all linked to the same `execution_id`.

This table is what powers the frontend canvas colouring (green/red per node) and the per-node input/output side panel.

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
| `execution_id` | UUID | NO | — | FK to `executions`. Groups all node results for one run together. |
| `node_id` | VARCHAR(50) | NO | — | The node's `id` from `definition` JSONB — e.g. `"n1"`, `"n2"`. This is the bridge back to the canvas. |
| `node_type` | VARCHAR(50) | NO | — | e.g. `"if_else"`, `"manual_trigger"`. Stored here so logs are readable without joining `workflows`. |
| `status` | VARCHAR(20) | NO | `'PENDING'` | Current state of this node's execution. See [Status Values](#status-values-reference). |
| `input_data` | JSONB | YES | NULL | The JSON this node received from the previous node. Null for trigger nodes (nothing comes before them). |
| `output_data` | JSONB | YES | NULL | The JSON this node produced and passed to the next node. Null if node failed before producing output. |
| `error_message` | TEXT | YES | NULL | If this specific node failed, the reason. Null if succeeded. |
| `started_at` | TIMESTAMPTZ | YES | NULL | When this node started executing. |
| `finished_at` | TIMESTAMPTZ | YES | NULL | When this node finished. `finished_at - started_at` = node execution duration. |

#### Notes
- `node_id` must match exactly with the `id` field inside `workflows.definition.nodes[*].id`. Anil uses this to map execution results back to canvas nodes.
- Rows for nodes that were never reached (e.g. after a failure) stay with `status = 'PENDING'` and all nullable fields as NULL.
- `input_data` and `output_data` are the most important columns for debugging — always populate them.

#### Real Example

Workflow with 4 nodes, one run, `n3` fails:

| node_id | node_type | status | input_data | output_data | error_message |
|---|---|---|---|---|---|
| n1 | manual_trigger | SUCCEEDED | NULL | `{"triggered": true}` | NULL |
| n2 | filter | SUCCEEDED | `{"items": [...]}` | `{"items": [2 matched]}` | NULL |
| n3 | if_else | FAILED | `{"items": [...]}` | NULL | `"field 'status' not found in input"` |
| n4 | aggregate | PENDING | NULL | NULL | NULL |

---

### 5. `app_credentials`

Stores OAuth tokens and API keys for third-party app integrations per user. Each row is one connected app for one user.

> ⚠️ **Phase 3 only.** Create this table now in the migration so it exists, but no code reads or writes to it until Phase 3.

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
| `id` | UUID | NO | `gen_random_uuid()` | Primary key. This ID is referenced by action nodes in the workflow definition. |
| `user_id` | UUID | NO | — | FK to `users`. Credentials are strictly per-user — no sharing. |
| `app_name` | VARCHAR(50) | NO | — | Which app. One of: `gmail`, `sheets`, `telegram`, `whatsapp`, `linkedin`. |
| `token_data` | JSONB | NO | — | The actual token(s). Shape varies by app — see below. |
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
- `token_data` is JSONB because different apps need different fields — one flexible column handles all.
- In Phase 3, action nodes store `credential_id` (this table's `id`) in their config, never the raw token.
- Token values are stored as plain text for prototype. Encryption can be added in a future version.

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
| `workflow_id` | UUID | NO | — | FK to `workflows`. Which workflow to trigger on incoming POST. |
| `user_id` | UUID | NO | — | FK to `users`. Owner. Used for authorization. |
| `node_id` | VARCHAR(50) | NO | — | Which node inside the workflow is the webhook trigger — e.g. `"n1"`. |
| `path_token` | VARCHAR(100) | NO | — | The random token in the public URL. **Must be globally unique.** |
| `is_active` | BOOLEAN | NO | `true` | If `false`, incoming POSTs return 404. Linked to `workflows.is_published`. |
| `created_at` | TIMESTAMPTZ | NO | `now()` | When the webhook was registered. |

#### Notes
- `path_token` is auto-generated by the backend (use `secrets.token_urlsafe(16)`) when a workflow containing a Webhook Trigger node is saved for the first time.
- The full public URL is: `POST /webhook/{path_token}`
- Anil reads this URL from the API and displays it in the Webhook node config panel so users can copy it.
- `is_active` must be set to `false` automatically when `workflows.is_published` is set to `false`. This is handled in the WorkflowService, not at DB level.
- `ON DELETE CASCADE` on `workflow_id` — deleting a workflow removes its webhook registrations.

---

## Relationships

```
users
 ├── workflows        (user_id → users.id)
 │    ├── executions          (workflow_id → workflows.id)
 │    │    └── node_executions (execution_id → executions.id)
 │    └── webhook_endpoints   (workflow_id → workflows.id)
 ├── executions       (user_id → users.id)
 ├── app_credentials  (user_id → users.id)
 └── webhook_endpoints (user_id → users.id)
```

**All foreign keys use `ON DELETE CASCADE`** — deleting a user removes all their data. Deleting a workflow removes all its executions, node executions, and webhook endpoints.

---

## Workflow Definition JSON Structure

The `workflows.definition` JSONB column stores the full canvas. Every team member must agree on this structure — it is the contract between backend (DAG executor) and frontend (React Flow).

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
        "value": "active"
      }
    },
    {
      "id": "n3",
      "type": "filter",
      "label": "Filter Items",
      "position": { "x": 600, "y": 100 },
      "config": {
        "field": "amount",
        "operator": "greater_than",
        "value": "100"
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
| `id` | string | YES | Unique within this workflow. e.g. `"n1"`, `"n2"`. Frontend generates this. Must match `node_executions.node_id`. |
| `type` | string | YES | Node type key. See full list below. |
| `label` | string | YES | Human-readable name shown on the canvas node. |
| `position` | object | YES | `{ "x": number, "y": number }`. Canvas coordinates. Used by React Flow. |
| `config` | object | YES | Node-specific configuration. Shape varies by type. Can be `{}` for nodes with no config. |

### Edge Object Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | YES | Unique within this workflow. e.g. `"e1"`. |
| `source` | string | YES | `id` of the source node. |
| `target` | string | YES | `id` of the target node. |
| `branch` | string | NO | Only for IF/Else and Switch nodes. Value is `"true"`, `"false"`, or a case label. |

### All Node Type Keys

#### Trigger Nodes
| type key | Status | Description |
|---|---|---|
| `manual_trigger` | ✅ Live — Phase 1 | User clicks Run |
| `form_trigger` | ✅ Live — Phase 1 | Form submission starts the workflow |
| `webhook_trigger` | ✅ Live — Phase 1 | External POST to registered URL |
| `workflow_trigger` | 🔘 Dummy — future | Triggers another workflow |

#### Action Nodes (all dummy until Phase 3)
| type key | Status |
|---|---|
| `get_gmail_message` | 🔘 Dummy — Phase 3 |
| `send_gmail_message` | 🔘 Dummy — Phase 3 |
| `create_google_sheets` | 🔘 Dummy — Phase 3 |
| `search_update_google_sheets` | 🔘 Dummy — Phase 3 |
| `telegram` | 🔘 Dummy — Phase 3 |
| `whatsapp` | 🔘 Dummy — Phase 3 |
| `linkedin` | 🔘 Dummy — Phase 3 |

#### Data Transformation Nodes
| type key | Status |
|---|---|
| `if_else` | ✅ Live — Phase 1 |
| `switch` | ✅ Live — Phase 1 |
| `merge` | ✅ Live — Phase 1 |
| `filter` | ✅ Live — Phase 1 |
| `datetime_format` | ✅ Live — Phase 1 |
| `split_in` | ✅ Live — Phase 1 |
| `split_out` | ✅ Live — Phase 1 |
| `aggregate` | ✅ Live — Phase 1 |

#### AI Node
| type key | Status |
|---|---|
| `ai_agent` | ✅ Live — Phase 2 |

---

## Status Values Reference

Both `executions.status` and `node_executions.status` use the same 4 values:

| Value | Meaning |
|---|---|
| `PENDING` | Created, waiting to be picked up by Celery worker |
| `RUNNING` | Currently executing |
| `SUCCEEDED` | Completed successfully |
| `FAILED` | Encountered an error |

### Valid Transitions

```
PENDING → RUNNING → SUCCEEDED
                  → FAILED
```

No other transitions are valid. A SUCCEEDED or FAILED row is never updated again.

---

## Important Rules — Read Before Writing Code

> These rules are non-negotiable. Every team member must follow them.

### 1. Always filter by user_id
Every query that returns data must include a `WHERE user_id = :current_user_id` clause. Never return data without this filter. This is how user separation is enforced.

```python
# ✅ Correct
db.query(Workflow).filter(Workflow.user_id == current_user.id)

# ❌ Wrong — returns all users' workflows
db.query(Workflow).all()
```

### 2. Never expose hashed_password in API responses
The `users` table has `hashed_password`. It must never appear in any API response. Use a separate Pydantic response schema that excludes it.

### 3. node_id in node_executions must match definition
When the DAG executor creates `node_executions` rows, `node_id` must be copied exactly from `workflow.definition.nodes[*].id`. Anil depends on this exact match to colour canvas nodes.

### 4. updated_at on workflows must always be current
Every time a workflow is saved via `PUT /workflows/{id}`, the `updated_at` column must be updated to `now()`. Do not forget this.

### 5. Webhook path_token is immutable
Once a `webhook_endpoints` row is created, `path_token` must never change. External services (GitHub, Stripe, etc.) will have registered this URL — changing it breaks their integration.

### 6. app_credentials — do not implement in Phase 1 or 2
The table exists in the DB. Do not write any service logic, routes, or runners that read from it until Phase 3 starts.

---

*This document is maintained by Ishika. Any schema change must be discussed with the full team and this file must be updated before the migration is written.*

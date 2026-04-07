---
description:  This document is the **single source of truth** for the database schema of the Workflow Automation Platform. Every table, every column, and every design decision is documented here.
---


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
- `token_data` is JSONB because different apps need different fields 
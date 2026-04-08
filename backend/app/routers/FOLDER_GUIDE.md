# Routers Folder

This folder contains FastAPI route modules.

Files that belong here:
- `auth.py` for signup, login, and current user routes
- `workflows.py` for workflow CRUD endpoints
- `executions.py` for run and status endpoints
- `ai.py` for workflow generation endpoints
- `credentials.py` and `webhooks.py` for integration-related APIs

Why this folder exists:
- To define the public API surface of the backend
- To keep endpoint declarations organized by feature
- To keep route handlers thin and delegate business work to services

Do not put here:
- heavy business logic
- direct external API orchestration
- complex DAG execution code

# API Request & Response Payload Contract
# Workflow Automation Platform

> **Owner:** Ishika    
> **Last updated:** April 2026   
> **Version:** 1.0    
> **Status:** ✅ Locked for Phase 1 & 2 — Phase 3 contracts defined, implementation pending    

---

## Table of Contents

1. [How to Read This Document](#how-to-read-this-document)
2. [Global Rules](#global-rules)
3. [Error Response Format](#error-response-format)
4. [Auth Endpoints](#auth-endpoints)
   - [POST /auth/signup](#1-post-authsignup)
   - [POST /auth/login](#2-post-authlogin)
   - [GET /auth/me](#3-get-authme)
5. [Workflow Endpoints](#workflow-endpoints)
   - [POST /workflows](#4-post-workflows)
   - [GET /workflows](#5-get-workflows)
   - [GET /workflows/{id}](#6-get-workflowsid)
   - [PUT /workflows/{id}](#7-put-workflowsid)
   - [DELETE /workflows/{id}](#8-delete-workflowsid)
6. [Execution Endpoints](#execution-endpoints)
   - [POST /workflows/{id}/run](#9-post-workflowsidrun)
   - [POST /workflows/{id}/run-form](#10-post-workflowsidrun-form)
   - [POST /webhook/{path_token}](#11-post-webhookpath_token)
   - [GET /executions/{id}](#12-get-executionsid)
   - [GET /executions](#13-get-executions)
7. [AI Workflow Builder Endpoint](#ai-workflow-builder-endpoint)
   - [POST /ai/generate-workflow](#14-post-aigenerate-workflow)
8. [Credentials Endpoints — Phase 3](#credentials-endpoints--phase-3)
   - [POST /credentials](#15-post-credentials)
   - [GET /credentials](#16-get-credentials)
   - [DELETE /credentials/{id}](#17-delete-credentialsid)
   - [OAuth Endpoints](#oauth-endpoints-gmail--linkedin)
9. [Pagination Strategy](#pagination-strategy)
10. [Quick Reference Table](#quick-reference-table)

---

## How to Read This Document

This document is the **single source of truth for all API request and response shapes** across the platform.

- **Person 1 (Anokhi/ Backend)** — implement endpoints to match these exact shapes
- **Person 2 (Ishika / Backend)** — owns this document, implements Workflow CRUD + node runners
- **Person 3 (Anil / Frontend)** — consume these exact shapes, do not expect fields not listed here

> **Rule:** If a field is not in this document, it does not exist in the API. If you need a new field, discuss with the team and update this document first — before writing any code.

---

## Global Rules

These apply to every single endpoint without exception.

### Authentication
- Every endpoint except `POST /auth/signup`, `POST /auth/login`, and `POST /webhook/{path_token}` requires a JWT
- JWT must be sent in the `Authorization` header as: `Authorization: Bearer <token>`
- If JWT is missing or invalid → `401 Unauthorized`

### User Isolation
- Every query filters by `user_id` from the JWT — users never see each other's data
- This applies to workflows, executions, credentials — everything

### Sensitive Fields — Never Exposed
- `hashed_password` — never returned in any response under any circumstance
- `token_data` (credentials) — never returned in any response under any circumstance
- These fields exist in the DB but must be excluded from every Pydantic response schema

### UUIDs
- All `id` fields are UUIDs — e.g. `"a1b2c3d4-0000-0000-0000-000000000001"`
- Never use integers as IDs

### Timestamps
- All timestamps are `TIMESTAMPTZ` in DB, returned as **ISO 8601 strings in UTC**
- Format: `"2026-04-07T10:00:00Z"`

### 404 Behaviour — Security Rule
- When a resource doesn't exist OR exists but belongs to another user → always return **the same `404`**
- Never reveal that another user's resource exists
- Example: `GET /workflows/{id}` returns 404 whether the workflow doesn't exist or belongs to someone else

---

## Error Response Format

All errors across all endpoints follow this consistent shape:

```json
{
  "detail": "Human-readable error message here"
}
```

### HTTP Status Codes Used

| Code | Meaning | When |
|---|---|---|
| `200` | OK | Successful GET, PUT, DELETE |
| `201` | Created | Successful POST that creates a resource |
| `202` | Accepted | POST that enqueues a background task (executions) |
| `400` | Bad Request | Malformed request body |
| `401` | Unauthorized | Missing or invalid JWT |
| `403` | Forbidden | Valid JWT but not allowed (rare — prefer 404 for ownership) |
| `404` | Not Found | Resource doesn't exist or belongs to another user |
| `422` | Unprocessable Entity | Validation error (e.g. AI returned invalid workflow JSON) |
| `500` | Internal Server Error | Unexpected backend crash |

---

## Auth Endpoints

---

### 1. `POST /auth/signup`

Register a new user account.

**Request Body:**
```json
{
  "email": "ishika@example.com",
  "username": "ishika",
  "password": "mypassword123"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | YES | Login identifier. Must be unique. |
| `username` | string | YES | Display name shown in UI. Must be unique. |
| `password` | string | YES | Plain text — backend hashes with bcrypt before storing. |

**Response `201 Created`:**
```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000001",
  "email": "ishika@example.com",
  "username": "ishika",
  "created_at": "2026-04-07T10:00:00Z"
}
```

**Response `400 Bad Request`** — duplicate email or username:
```json
{
  "detail": "Email already registered"
}
```

> `hashed_password` is NEVER returned. Signup does not return a token — user must call `/auth/login` separately.

---

### 2. `POST /auth/login`

Authenticate and receive a JWT access token.

**Request Body:**
```json
{
  "email": "ishika@example.com",
  "password": "mypassword123"
}
```

**Response `200 OK`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Response `401 Unauthorized`** — wrong email or password:
```json
{
  "detail": "Invalid email or password"
}
```

> Anil stores `access_token` in `localStorage`. All subsequent requests send it as `Authorization: Bearer <token>`.

---

### 3. `GET /auth/me`

Returns the currently authenticated user's info.

**Request:** No body. JWT in `Authorization` header.

**Response `200 OK`:**
```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000001",
  "email": "ishika@example.com",
  "username": "ishika",
  "created_at": "2026-04-07T10:00:00Z"
}
```

---

## Workflow Endpoints

---

### 4. `POST /workflows`

Create a new workflow. Always starts as a draft (`is_published: false`).

**Request Body:**
```json
{
  "name": "Order Processing Workflow",
  "description": "Filters orders above 500 and checks payment status",
  "definition": {
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
        "type": "filter",
        "label": "Filter High Value Orders",
        "position": { "x": 350, "y": 150 },
        "config": {
          "input_key": "items",
          "field": "amount",
          "operator": "greater_than",
          "value": "500"
        }
      },
      {
        "id": "n3",
        "type": "if_else",
        "label": "Check Payment Status",
        "position": { "x": 600, "y": 150 },
        "config": {
          "field": "status",
          "operator": "equals",
          "value": "paid"
        }
      }
    ],
    "edges": [
      { "id": "e1", "source": "n1", "target": "n2" },
      { "id": "e2", "source": "n2", "target": "n3", "branch": "true" }
    ]
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | YES | Max 100 characters. |
| `description` | string | NO | Optional. Can be omitted entirely. |
| `definition` | object | YES | Full canvas — nodes + edges. See DB Schema doc for full definition structure. |

> `is_published` is **NOT sent by the client** on creation. Backend always sets it to `false`. Client uses `PUT /workflows/{id}` to publish later.

**Response `201 Created`:**
```json
{
  "id": "wf-uuid-0001",
  "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "name": "Order Processing Workflow",
  "description": "Filters orders above 500 and checks payment status",
  "definition": {
    "nodes": ["..."],
    "edges": ["..."]
  },
  "is_published": false,
  "created_at": "2026-04-07T10:00:00Z",
  "updated_at": "2026-04-07T10:00:00Z"
}
```

---

### 5. `GET /workflows`

List all workflows for the current user. Supports pagination.

**Query Parameters:**

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `limit` | integer | NO | `20` | Number of results to return. |
| `offset` | integer | NO | `0` | Number of results to skip. |

**Example:** `GET /workflows?limit=20&offset=0`

**Response `200 OK`:**
```json
{
  "total": 24,
  "limit": 20,
  "offset": 0,
  "next_cursor": null,
  "workflows": [
    {
      "id": "wf-uuid-0001",
      "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
      "name": "Order Processing Workflow",
      "description": "Filters orders above 500 and checks payment status",
      "is_published": false,
      "created_at": "2026-04-07T10:00:00Z",
      "updated_at": "2026-04-07T10:00:00Z"
    },
    {
      "id": "wf-uuid-0002",
      "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
      "name": "Webhook Listener",
      "description": null,
      "is_published": true,
      "created_at": "2026-04-06T08:00:00Z",
      "updated_at": "2026-04-06T09:30:00Z"
    }
  ]
}
```

> **Important — `definition` is intentionally excluded from this list response.** The full JSONB definition can be very large. List view only needs metadata for rendering workflow cards. Anil fetches the full definition only when the user clicks to open a specific workflow via `GET /workflows/{id}`.

> **Pagination note — `next_cursor` field:** We are using limit/offset pagination for Phase 1 MVP. However `next_cursor` is included in the response shape now (always `null` for now) so that when we upgrade to cursor-based pagination in the future, Anil's frontend code does not need to change. Do not implement cursor logic now — just return `null`.

> **Why cursor pagination in the future?** Offset pagination has two real-world problems: (1) rows shift when items are added/deleted mid-pagination causing duplicates or skipped items, and (2) large offsets force PostgreSQL to scan and discard rows making it slower as data grows. Cursor pagination avoids both by using a `WHERE updated_at < last_seen` clause instead of `OFFSET`. We keep it simple for the MVP and upgrade later.

---

### 6. `GET /workflows/{id}`

Fetch a single workflow with its full definition.

**Request:** No body. JWT in header.

**Response `200 OK`:**
```json
{
  "id": "wf-uuid-0001",
  "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "name": "Order Processing Workflow",
  "description": "Filters orders above 500 and checks payment status",
  "definition": {
    "nodes": [
      {
        "id": "n1",
        "type": "manual_trigger",
        "label": "Start",
        "position": { "x": 100, "y": 150 },
        "config": {}
      }
    ],
    "edges": []
  },
  "is_published": false,
  "created_at": "2026-04-07T10:00:00Z",
  "updated_at": "2026-04-07T10:00:00Z"
}
```

**Response `404 Not Found`:**
```json
{
  "detail": "Workflow not found"
}
```

> 404 is returned both when the workflow doesn't exist AND when it belongs to another user. Never reveal that another user's workflow exists.

---

### 7. `PUT /workflows/{id}`

Partial update — client sends only the fields that changed. At least one field must be present.

**Request Body (updating name and publishing):**
```json
{
  "name": "Order Processing Workflow v2",
  "is_published": true
}
```

**Request Body (saving canvas changes only):**
```json
{
  "definition": {
    "nodes": ["..."],
    "edges": ["..."]
  }
}
```

**Request Body (updating description only):**
```json
{
  "description": "Updated description"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | NO | Max 100 characters. |
| `description` | string | NO | Pass `null` to clear it. |
| `definition` | object | NO | Full canvas replacement — always send complete definition, not a diff. |
| `is_published` | boolean | NO | `true` = live and triggerable. `false` = draft. |

> **`updated_at` is always refreshed on every PUT** — this is non-negotiable per the schema rules. Powers "sort by recently edited" in the UI.

> **Side effect of `is_published: false`:** Backend must also set `webhook_endpoints.is_active = false` for all webhooks belonging to this workflow. This is handled in `WorkflowService` — not at DB level. Anokhi owns this logic.

> **`is_published` lives here in PUT** — we considered a separate `PUT /workflows/{id}/publish` endpoint but decided to keep it simple and avoid extra endpoints for MVP.

**Response `200 OK`:**
```json
{
  "id": "wf-uuid-0001",
  "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "name": "Order Processing Workflow v2",
  "description": "Filters orders above 500 and checks payment status",
  "definition": {
    "nodes": ["..."],
    "edges": ["..."]
  },
  "is_published": true,
  "created_at": "2026-04-07T10:00:00Z",
  "updated_at": "2026-04-07T11:45:00Z"
}
```

---

### 8. `DELETE /workflows/{id}`

Delete a workflow and all its associated data.

**Request:** No body. JWT in header.

**Response `200 OK`:**
```json
{
  "message": "Workflow deleted successfully"
}
```

**Response `404 Not Found`:**
```json
{
  "detail": "Workflow not found"
}
```

> `ON DELETE CASCADE` in the DB automatically removes all `executions`, `node_executions`, and `webhook_endpoints` rows for this workflow.

---

## Execution Endpoints

---

### 9. `POST /workflows/{id}/run`

Manually trigger a workflow execution. User clicks **Run** in the UI.

**Request:** No body. JWT in header is sufficient — backend knows the user and workflow.

**Response `202 Accepted`:**
```json
{
  "execution_id": "exec-uuid-0001",
  "workflow_id": "wf-uuid-0001",
  "status": "PENDING",
  "triggered_by": "manual"
}
```

> **202 Accepted, not 200 OK** — the workflow has NOT executed yet. It has been enqueued in Celery. Anil immediately starts polling `GET /executions/{execution_id}` every 2 seconds using the returned `execution_id`.

---

### 10. `POST /workflows/{id}/run-form`

Trigger a workflow via a Form Trigger node. User fills out a form in the UI and submits.

**Request Body:**
```json
{
  "form_data": {
    "customer_name": "Rahul Sharma",
    "email": "rahul@example.com",
    "order_amount": "1500"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `form_data` | object | YES | Key-value pairs from the form. All values are strings. Runner handles casting if needed. |

**Response `202 Accepted`:**
```json
{
  "execution_id": "exec-uuid-0002",
  "workflow_id": "wf-uuid-0001",
  "status": "PENDING",
  "triggered_by": "form"
}
```

> `form_data` becomes the `output_data` of the Form Trigger node — i.e. it is what gets passed downstream to the next node.

---

### 11. `POST /webhook/{path_token}`

Inbound webhook from an external service (e.g. Stripe, GitHub, any third party).

> **This endpoint is fully public — no JWT required.** The `path_token` in the URL acts as the secret.

**Request** (sent by the external service — any valid JSON body):
```json
{
  "event": "order.created",
  "order_id": "ORD-9912",
  "amount": 1800,
  "status": "paid"
}
```

**Response `202 Accepted`:**
```json
{
  "execution_id": "exec-uuid-0003",
  "message": "Workflow execution enqueued"
}
```

**Response `404 Not Found`** — if `path_token` doesn't exist OR `is_active = false`:
```json
{
  "detail": "Webhook not found"
}
```

> **Two critical rules:**
> - The entire POST body is passed as-is and becomes the first node's `output_data` downstream
> - We return the **same 404** whether the token doesn't exist OR the workflow is unpublished — never leak information to external callers

---

### 12. `GET /executions/{id}`

Poll execution status and per-node results. **This is the most important endpoint for the frontend.**

Anil polls this every 2 seconds. **Stop polling when `finished_at` is not `null`.**

**Response `200 OK` — while still running:**
```json
{
  "id": "exec-uuid-0001",
  "workflow_id": "wf-uuid-0001",
  "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "status": "RUNNING",
  "triggered_by": "manual",
  "started_at": "2026-04-07T10:01:00Z",
  "finished_at": null,
  "error_message": null,
  "node_results": [
    {
      "node_id": "n1",
      "node_type": "manual_trigger",
      "status": "SUCCEEDED",
      "input_data": null,
      "output_data": { "triggered": true },
      "error_message": null,
      "started_at": "2026-04-07T10:01:00Z",
      "finished_at": "2026-04-07T10:01:01Z"
    },
    {
      "node_id": "n2",
      "node_type": "filter",
      "status": "RUNNING",
      "input_data": { "items": [{ "amount": 300 }, { "amount": 700 }] },
      "output_data": null,
      "error_message": null,
      "started_at": "2026-04-07T10:01:01Z",
      "finished_at": null
    },
    {
      "node_id": "n3",
      "node_type": "if_else",
      "status": "PENDING",
      "input_data": null,
      "output_data": null,
      "error_message": null,
      "started_at": null,
      "finished_at": null
    }
  ]
}
```

**Response `200 OK` — completed successfully:**
```json
{
  "id": "exec-uuid-0001",
  "workflow_id": "wf-uuid-0001",
  "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "status": "SUCCEEDED",
  "triggered_by": "manual",
  "started_at": "2026-04-07T10:01:00Z",
  "finished_at": "2026-04-07T10:01:05Z",
  "error_message": null,
  "node_results": [
    {
      "node_id": "n1",
      "node_type": "manual_trigger",
      "status": "SUCCEEDED",
      "input_data": null,
      "output_data": { "triggered": true },
      "error_message": null,
      "started_at": "2026-04-07T10:01:00Z",
      "finished_at": "2026-04-07T10:01:01Z"
    },
    {
      "node_id": "n2",
      "node_type": "filter",
      "status": "SUCCEEDED",
      "input_data": { "items": [{ "amount": 300 }, { "amount": 700 }, { "amount": 150 }] },
      "output_data": { "items": [{ "amount": 700 }] },
      "error_message": null,
      "started_at": "2026-04-07T10:01:01Z",
      "finished_at": "2026-04-07T10:01:03Z"
    },
    {
      "node_id": "n3",
      "node_type": "if_else",
      "status": "SUCCEEDED",
      "input_data": { "items": [{ "amount": 700 }] },
      "output_data": { "items": [{ "amount": 700 }], "_branch": "true" },
      "error_message": null,
      "started_at": "2026-04-07T10:01:03Z",
      "finished_at": "2026-04-07T10:01:05Z"
    }
  ]
}
```

**Response `200 OK` — completed with a node failure:**
```json
{
  "id": "exec-uuid-0001",
  "workflow_id": "wf-uuid-0001",
  "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "status": "FAILED",
  "triggered_by": "manual",
  "started_at": "2026-04-07T10:01:00Z",
  "finished_at": "2026-04-07T10:01:05Z",
  "error_message": null,
  "node_results": [
    {
      "node_id": "n1",
      "node_type": "manual_trigger",
      "status": "SUCCEEDED",
      "input_data": null,
      "output_data": { "triggered": true },
      "error_message": null,
      "started_at": "2026-04-07T10:01:00Z",
      "finished_at": "2026-04-07T10:01:01Z"
    },
    {
      "node_id": "n2",
      "node_type": "if_else",
      "status": "FAILED",
      "input_data": { "status": "pending", "amount": 700 },
      "output_data": null,
      "error_message": "field 'status' not found in input",
      "started_at": "2026-04-07T10:01:01Z",
      "finished_at": "2026-04-07T10:01:02Z"
    },
    {
      "node_id": "n3",
      "node_type": "aggregate",
      "status": "PENDING",
      "input_data": null,
      "output_data": null,
      "error_message": null,
      "started_at": null,
      "finished_at": null
    }
  ]
}
```

### `node_results` Field Reference

| Field | Type | Description |
|---|---|---|
| `node_id` | string | Matches exactly with `definition.nodes[*].id` — Anil uses this to colour canvas nodes |
| `node_type` | string | e.g. `"if_else"`, `"filter"` |
| `status` | string | `PENDING`, `RUNNING`, `SUCCEEDED`, or `FAILED` |
| `input_data` | object / null | What this node received. Always `null` for trigger nodes |
| `output_data` | object / null | What this node produced. `null` if node failed or hasn't run |
| `error_message` | string / null | Node-level error reason. `null` if succeeded |
| `started_at` | string / null | `null` for nodes not yet reached |
| `finished_at` | string / null | `null` for nodes not yet finished |

### Three Rules for Anil (Frontend)

1. **`finished_at` at execution level = polling signal.** `null` → keep polling. Has a value → stop polling
2. **`error_message` at execution level vs node level are different things.** Execution-level `error_message` is for crashes that happen before any node runs (e.g. DAG executor crash). Node-level `error_message` is for that specific node's failure
3. **Unreached nodes always appear in `node_results` with `status: PENDING` and all nulls.** They must still be rendered on the canvas — just with no colour change (neither green nor red)

---

### 13. `GET /executions`

Execution history list for the current user.

**Query Parameters:**

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `limit` | integer | NO | `20` | Number of results. |
| `offset` | integer | NO | `0` | Results to skip. |
| `workflow_id` | string (UUID) | NO | — | Filter by a specific workflow. |
| `status` | string | NO | — | Filter by status: `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`. |

**Example:** `GET /executions?limit=20&offset=0&workflow_id=wf-uuid-0001&status=FAILED`

**Response `200 OK`:**
```json
{
  "total": 45,
  "limit": 20,
  "offset": 0,
  "executions": [
    {
      "id": "exec-uuid-0001",
      "workflow_id": "wf-uuid-0001",
      "workflow_name": "Order Processing Workflow",
      "status": "SUCCEEDED",
      "triggered_by": "manual",
      "started_at": "2026-04-07T10:01:00Z",
      "finished_at": "2026-04-07T10:01:05Z",
      "error_message": null
    },
    {
      "id": "exec-uuid-0002",
      "workflow_id": "wf-uuid-0001",
      "workflow_name": "Order Processing Workflow",
      "status": "FAILED",
      "triggered_by": "webhook",
      "started_at": "2026-04-07T09:00:00Z",
      "finished_at": "2026-04-07T09:00:03Z",
      "error_message": null
    }
  ]
}
```

> **`node_results` is intentionally excluded from this list.** Full node results are only fetched via `GET /executions/{id}` when the user clicks a specific execution to inspect it.

> **`workflow_name` is included here** even though it requires a join — saves Anil an extra API call just to show the name in the history table UI.

---

## AI Workflow Builder Endpoint

---

### 14. `POST /ai/generate-workflow`

User types a plain-English prompt → backend calls OpenAI → returns a valid workflow definition ready to load onto the canvas.

**Phase:** Phase 2

**Request Body:**
```json
{
  "prompt": "Send a Telegram message whenever a webhook is received and the status field equals active"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt` | string | YES | Plain-English description of the workflow the user wants to build. |

**Response `200 OK`:**
```json
{
  "definition": {
    "nodes": [
      {
        "id": "n1",
        "type": "webhook_trigger",
        "label": "Webhook Trigger",
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
        "type": "telegram",
        "label": "Send Telegram Message",
        "position": { "x": 600, "y": 150 },
        "config": {
          "chat_id": "",
          "message_text": ""
        }
      }
    ],
    "edges": [
      { "id": "e1", "source": "n1", "target": "n2" },
      { "id": "e2", "source": "n2", "target": "n3", "branch": "true" }
    ]
  },
  "message": "Workflow generated successfully. Review and save when ready."
}
```

**Response `422 Unprocessable Entity`** — LLM returned invalid JSON or invalid node types after retry:
```json
{
  "detail": "Could not generate a valid workflow from your prompt. Please try rephrasing."
}
```

> **Three things to note:**
> - Config fields for dummy nodes like `telegram` are returned with **empty strings** — Anil renders them in the config panel for the user to fill in before saving
> - Backend validates the LLM output before returning — checks all node types are valid and all edge `source`/`target` values reference real node `id`s. If validation fails after one retry → 422
> - Phase 2 uses the **team's shared OpenAI key** in `.env`. Phase 3 switches to the user's own key from `app_credentials`

---

## Credentials Endpoints — Phase 3

> ⚠️ **Phase 3 only.** The `app_credentials` table exists in the DB now but **no service logic reads or writes to it until Phase 3 starts.** These contracts are defined now so the team can plan ahead. Do not implement any of this in Phase 1 or Phase 2.

---

### 15. `POST /credentials`

Store an API key or bot token for a third-party app.

> This endpoint is used **only for token-based apps** (Telegram, WhatsApp). For Gmail and LinkedIn, OAuth callbacks handle credential storage automatically — users do not call this endpoint directly for those apps.

**Request Body (Telegram):**
```json
{
  "app_name": "telegram",
  "token_data": {
    "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
  }
}
```

**Request Body (WhatsApp):**
```json
{
  "app_name": "whatsapp",
  "token_data": {
    "access_token": "EAAb...",
    "phone_number_id": "123456789"
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `app_name` | string | YES | One of: `gmail`, `sheets`, `telegram`, `whatsapp`, `linkedin` |
| `token_data` | object | YES | Shape varies by app — see DB Schema doc for full token_data shapes per app |

**Response `201 Created`:**
```json
{
  "id": "cred-uuid-0001",
  "user_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "app_name": "telegram",
  "created_at": "2026-04-07T10:00:00Z"
}
```

> `token_data` is **never returned** in any response — same principle as `hashed_password`. The `id` returned here is what node configs store as `credential_id` — never the raw token.

---

### 16. `GET /credentials`

List all connected apps for the current user. Used by Anil to render the Settings page — green tick / grey dash per app.

**Request:** No body. JWT in header.

**Response `200 OK`:**
```json
{
  "credentials": [
    {
      "id": "cred-uuid-0001",
      "app_name": "telegram",
      "created_at": "2026-04-07T10:00:00Z"
    },
    {
      "id": "cred-uuid-0002",
      "app_name": "gmail",
      "created_at": "2026-04-06T08:00:00Z"
    }
  ]
}
```

> `token_data` is never exposed here. Anil only needs `id` and `app_name` to show connected status and populate credential dropdowns inside node config panels.

---

### 17. `DELETE /credentials/{id}`

Disconnect an app — removes the stored credential.

**Request:** No body. JWT in header.

**Response `200 OK`:**
```json
{
  "message": "Credential removed successfully"
}
```

**Response `404 Not Found`:**
```json
{
  "detail": "Credential not found"
}
```

> Same 404 rule — identical response whether the credential doesn't exist or belongs to another user.

---

### OAuth Endpoints (Gmail + LinkedIn)

These are implemented by **Anokhi** but documented here so Anil knows what to expect on the frontend.

#### `GET /auth/google/connect`

**Request:** JWT in header.

**Response:** `302 Redirect` → Google OAuth consent screen

#### `GET /auth/google/callback`

Handled entirely by backend. Google redirects here after user approves.

**Response:** `302 Redirect` → Frontend Settings page on success

#### `GET /auth/linkedin/connect` + `GET /auth/linkedin/callback`

Same pattern as Google above.

> **For Anil:** Clicking **Connect** on Gmail or LinkedIn opens a new browser tab pointing to these URLs. Everything else — token exchange, storage in `app_credentials` — is handled server-side. Frontend just needs to refresh the credentials list after the OAuth tab closes.

---

## Pagination Strategy

### Current Implementation — Limit / Offset (Phase 1 MVP)

```
GET /workflows?limit=20&offset=0
GET /executions?limit=20&offset=0
```

Simple and sufficient for MVP. A user won't realistically have thousands of workflows or executions during the prototype phase.

### Future Upgrade — Cursor Pagination

**Why offset pagination has real-world problems:**
- If a workflow is added or deleted while a user is paginating, rows shift — they get duplicates or miss items entirely
- Large offsets (`OFFSET 10000`) force PostgreSQL to scan and discard all preceding rows, getting slower as data grows
- Not suitable for infinite scroll or real-time feeds
- Twitter, Instagram, GitHub, Notion — all use cursor pagination

**How cursor pagination works:**
```
GET /workflows?limit=20&cursor=eyJ1cGRhdGVkX2F0IjoiMjAyNi0wNC0wN...}
```
The cursor is a base64-encoded pointer — usually `updated_at + id` of the last item seen. Backend query becomes:
```sql
WHERE updated_at < :last_seen_updated_at
ORDER BY updated_at DESC
LIMIT 20
```
Stable, fast, index-friendly.

**Why `next_cursor: null` is in the response now:**

The list response includes `next_cursor: null` today so that when we upgrade to cursor pagination later, Anil's frontend code does not need to change — just start reading `next_cursor` instead of incrementing `offset`.

---

## Quick Reference Table

| # | Method | Endpoint | Auth | Phase | Description |
|---|---|---|---|---|---|
| 1 | POST | `/auth/signup` | ❌ Public | 1 | Register new user |
| 2 | POST | `/auth/login` | ❌ Public | 1 | Login, get JWT |
| 3 | GET | `/auth/me` | ✅ JWT | 1 | Get current user |
| 4 | POST | `/workflows` | ✅ JWT | 1 | Create workflow |
| 5 | GET | `/workflows` | ✅ JWT | 1 | List workflows (paginated) |
| 6 | GET | `/workflows/{id}` | ✅ JWT | 1 | Get single workflow |
| 7 | PUT | `/workflows/{id}` | ✅ JWT | 1 | Update workflow / publish |
| 8 | DELETE | `/workflows/{id}` | ✅ JWT | 1 | Delete workflow |
| 9 | POST | `/workflows/{id}/run` | ✅ JWT | 1 | Manual trigger |
| 10 | POST | `/workflows/{id}/run-form` | ✅ JWT | 1 | Form trigger |
| 11 | POST | `/webhook/{path_token}` | ❌ Public | 1 | Inbound webhook trigger |
| 12 | GET | `/executions/{id}` | ✅ JWT | 1 | Poll execution + node results |
| 13 | GET | `/executions` | ✅ JWT | 1 | Execution history list |
| 14 | POST | `/ai/generate-workflow` | ✅ JWT | 2 | Generate workflow from prompt |
| 15 | POST | `/credentials` | ✅ JWT | 3 | Store API key / bot token |
| 16 | GET | `/credentials` | ✅ JWT | 3 | List connected apps |
| 17 | DELETE | `/credentials/{id}` | ✅ JWT | 3 | Remove credential |
| 18 | GET | `/auth/google/connect` | ✅ JWT | 3 | Start Gmail/Sheets OAuth |
| 19 | GET | `/auth/google/callback` | ❌ Public | 3 | Google OAuth callback |
| 20 | GET | `/auth/linkedin/connect` | ✅ JWT | 3 | Start LinkedIn OAuth |
| 21 | GET | `/auth/linkedin/callback` | ❌ Public | 3 | LinkedIn OAuth callback |

---

*This document is maintained by Ishika. Any change to request or response shapes must be discussed with the full team and this document updated before any code is written.*

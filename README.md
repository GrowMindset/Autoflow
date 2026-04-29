# Workflow Automation Platform

This project is a workflow automation platform built with FastAPI, PostgreSQL, Celery, Redis, and React.

The current goal is to deliver the MVP in three phases:
- Phase 1: Drag-and-drop workflow builder with save, load, and run
- Phase 2: AI workflow generation and AI Agent node execution
- Phase 3: Real app integrations such as Gmail, Google Sheets, Telegram, WhatsApp, and LinkedIn

This README is a starter placeholder and will be expanded later with setup steps, architecture, API details, and deployment notes.


## Run The App (4 Required Commands)

Open 4 terminals and run these commands from the project root.

### Terminal 1: Backend API (FastAPI)
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Terminal 2: Frontend (React + Vite)
```bash
cd frontend
npm run dev
```

### Terminal 3: Celery Worker (workflow + node tests + system queue)
```bash
cd backend
celery -A celery_config:celery_app worker --pool=solo --loglevel=info
```

### Terminal 4: Celery Beat (required for schedule trigger recurring runs)
```bash
cd backend
celery -A celery_config:celery_app beat --loglevel=info
```

## Notes

- Schedule Trigger recurring execution needs both:
  - Celery worker running `system` queue.
  - Celery beat running.
- Without beat, schedule triggers will not auto-scan/run repeatedly.

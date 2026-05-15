from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.routers.ai import router as ai_router
from app.routers.auth import router as auth_router
from app.routers.executions import router as executions_router
from app.routers.workflows import router as workflows_router
from app.routers.credentials import router as credentials_router


def _frontend_dist_dir() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "frontend" / "dist"


def _resolve_frontend_asset(dist_dir: Path, relative_path: str) -> Path | None:
    cleaned = str(relative_path or "").lstrip("/")
    if not cleaned:
        return None

    dist_root = dist_dir.resolve()
    candidate = (dist_root / cleaned).resolve()
    try:
        candidate.relative_to(dist_root)
    except ValueError:
        return None

    if candidate.is_file():
        return candidate
    return None


def create_app() -> FastAPI:
    app = FastAPI()

    default_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.30.3:5173",
    ]
    env_origins = os.getenv("CORS_ALLOW_ORIGINS", "")
    parsed_env_origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    # Keep local defaults and let env origins extend the allow-list.
    allow_origins = list(dict.fromkeys([*default_origins, *parsed_env_origins]))
    allow_origin_regex = (
        os.getenv("CORS_ALLOW_ORIGIN_REGEX")
        or r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(ai_router)
    app.include_router(workflows_router)
    app.include_router(executions_router)
    app.include_router(credentials_router)
    frontend_dist_dir = _frontend_dist_dir()
    frontend_index_path = frontend_dist_dir / "index.html"

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/", include_in_schema=False)
    async def root():
        if frontend_index_path.is_file():
            return FileResponse(frontend_index_path)
        return {"message": "Welcome to the Autoflow!"}

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if not frontend_index_path.is_file():
            raise HTTPException(status_code=404, detail="Not Found")

        first_segment = str(full_path or "").split("/", 1)[0]
        if first_segment in {
            "auth",
            "ai",
            "workflows",
            "executions",
            "credentials",
            "webhook",
            "public",
            "health",
            "docs",
            "redoc",
            "openapi.json",
        }:
            raise HTTPException(status_code=404, detail="Not Found")

        asset = _resolve_frontend_asset(frontend_dist_dir, full_path)
        if asset is not None:
            return FileResponse(asset)

        return FileResponse(frontend_index_path)

    return app


app = create_app()

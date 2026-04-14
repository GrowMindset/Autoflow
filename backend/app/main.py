from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.routers.ai import router as ai_router
from app.routers.auth import router as auth_router
from app.routers.executions import router as executions_router
from app.routers.workflows import router as workflows_router
from app.routers.credentials import router as credentials_router


def create_app() -> FastAPI:
    app = FastAPI()

    default_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    env_origins = os.getenv("CORS_ALLOW_ORIGINS", "")
    parsed_env_origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    allow_origins = parsed_env_origins or default_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(ai_router)
    app.include_router(workflows_router)
    app.include_router(executions_router)
    app.include_router(credentials_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"message": "Welcome to the Autoflow!"}

    return app


app = create_app()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.executions import router as executions_router
from app.routers.workflows import router as workflows_router


def create_app() -> FastAPI:
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(workflows_router)
    app.include_router(executions_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"message": "Welcome to the Autoflow!"}

    return app


app = create_app()

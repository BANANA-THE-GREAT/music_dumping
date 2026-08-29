from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routes import router
from app.schemas import HealthResponse, ReadinessResponse


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.api_title, version=settings.api_version)
    init_db()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    def liveness() -> HealthResponse:
        return HealthResponse(service="api", version=settings.api_version)

    @app.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    def readiness() -> ReadinessResponse:
        return ReadinessResponse(
            service="api",
            version=settings.api_version,
            checks={"api": "ok"},
        )

    return app


app = create_app()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.job_runner import recover_interrupted_thread_jobs
from app.observability import RequestContextMiddleware
from app.routes import router
from app.schemas import HealthResponse, ReadinessResponse


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.api_title, version=settings.api_version)
    if settings.auto_create_schema:
        init_db()
    if settings.worker_backend == "thread":
        recover_interrupted_thread_jobs()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    def liveness() -> HealthResponse:
        return HealthResponse(service="api", version=settings.api_version)

    @app.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    def readiness() -> ReadinessResponse:
        database_status: str = "ok"
        try:
            with SessionLocal() as session:
                session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            database_status = "unavailable"
        return ReadinessResponse(
            service="api",
            version=settings.api_version,
            checks={"api": "ok", "database": database_status},
        )

    return app


app = create_app()

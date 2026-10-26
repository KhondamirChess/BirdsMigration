"""FastAPI application: wires the controllers, error handlers and the frontend.

Run from backend/:  uvicorn app.main:app --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from app.controllers import health_controller, simulator_controller
from app.core.config import get_settings
from app.core.database import SessionLocal, create_tables
from app.core.errors import AppError

log = logging.getLogger("hpai")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run on server startup: create the tables and load the demo data if the database is empty."""
    settings = get_settings()
    create_tables()
    if settings.seed_demo_on_startup:
        from scripts.seed_demo import seed_if_empty
        with SessionLocal() as session:
            seed_if_empty(session, settings)
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app: CORS, error handlers, API routes and the frontend static files."""
    settings = get_settings()
    app = FastAPI(title="Bird–HPAI Simulator API", version="0.2.0", lifespan=lifespan)
    # lets the page also work when opened as a file (origin "null")
    app.add_middleware(CORSMiddleware, allow_origins=["null", "http://localhost:8000", "http://127.0.0.1:8000"],
                       allow_methods=["GET"], allow_headers=["*"])

    @app.exception_handler(AppError)
    async def app_error(_req: Request, exc: AppError):
        """Turn an AppError raised by a service into a JSON error response with its status code."""
        return JSONResponse(status_code=exc.status_code,
                            content={"error": exc.code, "message": exc.message, "details": exc.details})

    @app.exception_handler(OperationalError)
    async def db_down(_req: Request, exc: OperationalError):
        """Return HTTP 503 with a clear message when PostgreSQL cannot be reached."""
        log.error("database error: %s", exc)
        return JSONResponse(status_code=503, content={"error": "database_unavailable",
                                                      "message": "PostgreSQL is not reachable.", "details": {}})

    app.include_router(health_controller.router)
    app.include_router(simulator_controller.router)
    if settings.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    return app


app = create_app()

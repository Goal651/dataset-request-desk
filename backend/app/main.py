"""FastAPI application: routes, middleware, error handling."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.domain import DomainError
from app.logging_config import configure_logging
from app.routers import analytics, assignments, auth, episodes, exports, requests, users

configure_logging()
logger = logging.getLogger("drd.request")

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Stretch: background work. Start the in-process export worker in dev."""
    if settings.environment != "test":
        from app.exporter import worker

        worker.start()
    yield
    if settings.environment != "test":
        from app.exporter import worker as _worker

        _worker.stop()


app = FastAPI(title="Dataset Request Desk", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """One structured log line per request + a session shared across dependencies."""
    request.state.request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex[:12])
    request.state.db = None
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "unhandled error",
            extra={
                "request_id": request.state.request_id,
                "method": request.method,
                "path": request.url.path,
                "status": 500,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    duration_ms = (time.perf_counter() - start) * 1000

    user_id = None
    db: Session | None = getattr(request.state, "db", None)
    if db is not None:
        user = getattr(request.state, "user", None)
        if user is not None:
            user_id = user.id
    logger.info(
        "request",
        extra={
            "request_id": request.state.request_id,
            "user_id": user_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 1),
        },
    )
    response.headers["X-Request-Id"] = request.state.request_id
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness + DB reachability for container orchestration."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unavailable"
    finally:
        db.close()
    return {"status": "ok", "database": db_status}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(episodes.router)
app.include_router(requests.router)
app.include_router(assignments.router)
app.include_router(analytics.router)
app.include_router(exports.router)

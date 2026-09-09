"""Academic Document Translator — FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hmac
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.logging_config import get_logger, setup_logging
from app.db.database import init_db
from app.services.jobs.manager import JobManager
from app.services.terminology.seed import seed_default_terminology
from app.utils.files import cleanup_temp_files

logger = get_logger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


async def _periodic_temp_cleanup() -> None:
    """Clean abandoned temp files periodically (uploads/outputs are never touched)."""
    while True:
        await asyncio.sleep(3600)
        try:
            cleanup_temp_files()
        except Exception:  # pragma: no cover
            logger.warning("Temp cleanup failed", extra={"operation": "temp_cleanup", "status": "error"})


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings.ensure_directories()
    init_db()

    from app.db.database import SessionLocal

    with SessionLocal() as db:
        inserted = seed_default_terminology(db)
    if inserted:
        logger.info(
            f"Seeded {inserted} default terminology entries",
            extra={"operation": "startup", "status": "success"},
        )

    app.state.jobs = JobManager()
    app.state.jobs.recover_interrupted_jobs()
    cleanup_temp_files()
    cleanup_task = asyncio.create_task(_periodic_temp_cleanup())
    logger.info(
        f"{settings.app_name} started",
        extra={
            "operation": "startup",
            "status": "success",
            "provider_configured": settings.provider_configured,
        },
    )
    try:
        yield
    finally:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        await app.state.jobs.provider.aclose()
        logger.info("Application shutdown", extra={"operation": "shutdown", "status": "success"})


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Translate large academic documents from English to Arabic with an AgentRouter-compatible LLM API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "provider_configured": settings.provider_configured,
    }


# Paths that must stay reachable without the site password (platform probes).
_PUBLIC_PATHS = {"/api/health", "/healthz"}


@app.middleware("http")
async def access_control_middleware(request: Request, call_next):
    """Optional site-wide password protection.

    When APP_ACCESS_PASSWORD is set, requests must carry HTTP Basic
    credentials with that password (any username). The browser prompts the
    visitor once, then attaches the credentials automatically to every
    same-origin request (SPA, API, file downloads). Health probes stay open.
    The API key itself never leaves the server either way.
    """
    password = settings.app_access_password
    if password:
        path = request.url.path.rstrip("/") or "/"
        if path not in _PUBLIC_PATHS and request.method != "OPTIONS":
            authorized = False
            header = request.headers.get("Authorization", "")
            if header.startswith("Basic "):
                try:
                    decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
                    supplied = decoded.split(":", 1)[1] if ":" in decoded else decoded
                    authorized = hmac.compare_digest(
                        supplied.encode("utf-8"), password.encode("utf-8")
                    )
                except (ValueError, UnicodeDecodeError):
                    authorized = False
            if not authorized:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "This site is password protected."},
                    headers={
                        "WWW-Authenticate": 'Basic realm="Academic Document Translator"'
                    },
                )
    return await call_next(request)


@app.get("/healthz")
async def healthz():
    """Root-level health probe (unauthenticated, for platform checks)."""
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Never leak stack traces to end users unless DEBUG is enabled."""
    logger.error(
        f"Unhandled error: {type(exc).__name__}: {exc}",
        extra={"operation": "request", "status": "error", "error_type": type(exc).__name__},
    )
    detail = (
        f"{type(exc).__name__}: {exc}"
        if settings.debug
        else "An internal error occurred. Check the server logs for details."
    )
    return JSONResponse(status_code=500, content={"detail": detail})


# ---- Serve the built frontend (production mode) ------------------------
if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        if full_path.startswith("api"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))

"""FastAPI application entry point."""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from db import init_db
from routers import personas, survey, report, followup, history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class _ReadyEndpointFilter(logging.Filter):
    """Suppress noisy 503 access-log lines from /ready polling."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not ("/ready" in msg and "503" in msg)


logging.getLogger("uvicorn.access").addFilter(_ReadyEndpointFilter())

_db_ready = threading.Event()


def _init_db_background():
    try:
        init_db()
        _db_ready.set()
        logger.info("Databases ready.")
    except Exception:
        logger.exception("Database initialization failed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initializing databases in background...")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _init_db_background)
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Nemotron Financial Survey Demo",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(personas.router)
app.include_router(survey.router)
app.include_router(report.router)
app.include_router(followup.router)
app.include_router(history.router)


@app.get("/health")
async def health():
    from llm import check_llm_health
    reachable = await check_llm_health()
    return {
        "status": "ok",
        "mock_llm": settings.mock_llm,
        "llm_reachable": reachable,
    }


@app.get("/ready")
async def ready():
    if _db_ready.is_set():
        return {"status": "ready"}
    return JSONResponse({"status": "loading"}, status_code=503)


# Serve frontend static build (must be after all API routes)
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    # Serve /assets/* (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve index.html for all non-API, non-asset routes (SPA fallback)."""
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import init_db
from routers import personas, survey, report, followup, history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initializing databases...")
    init_db()
    logger.info("Databases ready.")
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
    return {"status": "ok", "mock_llm": settings.mock_llm}

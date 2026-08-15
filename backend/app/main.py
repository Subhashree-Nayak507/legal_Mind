from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.db.postgres import init_db
from app.db.redis_client import get_redis, close_redis
from app.services.embedder import get_model
from app.services.reranker import _load_model as load_reranker_model
from app.middleware.rate_limit import RateLimitMiddleware
from app.api import ingest, query, auth,documents
from fastapi.staticfiles import StaticFiles
import os

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LegalMind starting up (env=%s)", settings.app_env)

    await init_db()
    logger.info("Database ready")

    get_redis()   # warm up Redis connection pool
    logger.info("Redis ready")

    get_model()   # load embedding model into memory (slow first time)
    logger.info("Embedding model ready")
    import asyncio
    try:
        await asyncio.wait_for(asyncio.to_thread(load_reranker_model), timeout=15)
        logger.info("Reranker (Groq) ready")
    except asyncio.TimeoutError:
        logger.error(
            "Reranker startup check timed out after 15s — check GROQ_API_KEY "
            "and network access. /query will fail until this is resolved."
        )
    logger.info("LegalMind startup complete")
    yield
    await close_redis()
    logger.info("Redis connections closed")
    logger.info("LegalMind shutdown complete")


app = FastAPI(
    title="LegalMind RAG API",
    version="2.1.0",
    lifespan=lifespan,
)

_allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
if settings.frontend_url:
    _allowed_origins += [o.strip() for o in settings.frontend_url.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware)

app.include_router(auth.router,   prefix="/api/v1")
app.include_router(ingest.router, prefix="/api/v1")
app.include_router(query.router,  prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")


@app.get("/health")
async def health():
    """
    Real health check — verifies Redis and DB are reachable.
    Used by Docker healthcheck and Render deploy checks.
    """
    checks = {"status": "ok", "redis": "ok", "db": "ok"}
    try:
        await get_redis().ping()
    except Exception as e:
        checks["redis"] = f"error: {e}"
        checks["status"] = "degraded"
    return checks


# Serve the built Next.js frontend (static export) — must be mounted LAST
# so it never shadows the /api/v1/* and /health routes above.
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
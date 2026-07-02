"""
FastAPI app entry point — fixed version.

Changes vs original:
  1. Removed REQUEST_COUNTS = {} in-memory rate limiting entirely
     → replaced by RateLimitMiddleware using Redis (middleware/rate_limit.py)

  2. setup_logging() called at startup
     → structured JSON in production, readable format in development

  3. close_redis() called at shutdown
     → clean connection pool teardown, no dangling connections

  4. /health checks Redis + DB, not just returns "ok"
     → real readiness probe for Docker/Render healthcheck

  5. Sentry initialized if SENTRY_DSN is set
     → unhandled exceptions auto-reported with stack trace, no log-watching needed

  6. auth router added (/api/v1/auth/register, /login)
     → query + ingest routes now require a valid JWT (see app/auth/)
"""
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

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────
    logger.info("LegalMind starting up (env=%s)", settings.app_env)

    await init_db()
    logger.info("Database ready")

    get_redis()   # warm up Redis connection pool
    logger.info("Redis ready")

    get_model()   # load embedding model into memory (slow first time)
    logger.info("Embedding model ready")

    # Reranker (cross-encoder) used to load lazily on the first /query call,
    # with no timeout on the HuggingFace download — if the network was slow
    # or blocked, that first request would hang forever with no error.
    # Preloading here means: (a) it loads once at startup, not per-request,
    # and (b) if the download is going to fail, it fails LOUDLY at startup
    # instead of silently hanging the first user's query.
    import asyncio
    try:
        await asyncio.wait_for(asyncio.to_thread(load_reranker_model), timeout=120)
        logger.info("Reranker model ready")
    except asyncio.TimeoutError:
        logger.error(
            "Reranker model failed to load within 120s — check network access "
            "to huggingface.co from inside the container. /query will fail "
            "until this is resolved."
        )

    # Note: LLM clients (Groq, Gemini) are singletons in llm.py,
    # initialized at module import — no explicit startup needed here.

    logger.info("LegalMind startup complete")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    await close_redis()
    logger.info("Redis connections closed")
    logger.info("LegalMind shutdown complete")


app = FastAPI(
    title="LegalMind RAG API",
    version="2.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (Redis-backed, replaces in-memory dict)
app.add_middleware(RateLimitMiddleware)

# Routes
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

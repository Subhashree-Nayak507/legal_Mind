"""
Embedder — now calls Gemini's embedding API instead of loading a local
sentence-transformers model.

Why: sentence-transformers pulls in torch, which alone uses 300-400MB of
RAM before any model weights load. On Render's free 512MB tier, that left
no room for the reranker or the rest of the app, causing OOM crashes.
Calling Gemini's hosted embedding endpoint removes torch from this service
entirely — same fail-fast-at-startup behavior, negligible memory.

Redis caching for embed_query() is unchanged.
"""
import hashlib
import json

import google.generativeai as genai
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis_client import get_redis

logger = get_logger(__name__)

genai.configure(api_key=settings.gemini_api_key)
_EMBED_MODEL = "models/gemini-embedding-001"  # current model; truncated to 768-dim below


def get_model() -> str:
    """
    Kept for compatibility with main.py's startup check. Makes one real
    API call so a bad/missing GEMINI_API_KEY fails loudly at boot instead
    of silently on the user's first query.
    """
    logger.info("[Embedder] Verifying Gemini embedding API: %s", _EMBED_MODEL)
    result = genai.embed_content(
        model=_EMBED_MODEL,
        content="startup healthcheck",
        task_type="retrieval_query",
        output_dimensionality=settings.embedding_dim,
    )
    if not result or "embedding" not in result:
        raise RuntimeError("Gemini embedding API did not return a vector")
    logger.info("[Embedder] Gemini embedding API ready (dim=%d)", settings.embedding_dim)
    return _EMBED_MODEL


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Used for document ingestion — one API call per chunk."""
    vectors = []
    for t in texts:
        result = genai.embed_content(
            model=_EMBED_MODEL,
            content=t,
            task_type="retrieval_document",
            output_dimensionality=settings.embedding_dim,
        )
        vectors.append(result["embedding"])
    return vectors


def _embedding_cache_key(text: str) -> str:
    normalized = text.strip().lower()
    return "legalmind:embcache:" + hashlib.sha256(normalized.encode()).hexdigest()


async def embed_query(text: str) -> list[float]:
    """
    Checks Redis cache first. Fails open: if Redis is down, falls straight
    through to calling the embedding API directly.
    """
    cache_key = _embedding_cache_key(text)
    try:
        cached = await get_redis().get(cache_key)
        if cached:
            logger.debug("[Embedder] Cache HIT for query embedding")
            return json.loads(cached)
    except RedisError as e:
        logger.warning("[Embedder] Cache get failed (continuing): %s", e)

    result = genai.embed_content(
        model=_EMBED_MODEL,
        content=text,
        task_type="retrieval_query",
        output_dimensionality=settings.embedding_dim,
    )
    vector = result["embedding"]

    try:
        await get_redis().setex(cache_key, settings.embedding_cache_ttl, json.dumps(vector))
    except RedisError as e:
        logger.warning("[Embedder] Cache set failed (non-fatal): %s", e)

    return vector
import hashlib
import json
import time

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis_client import get_redis

logger = get_logger(__name__)

genai.configure(api_key=settings.gemini_api_key)
_EMBED_MODEL = "models/gemini-embedding-001"  # current model; truncated to 768-dim below

# Gemini free tier returns 429 ResourceExhausted when the per-minute/per-day
# quota is hit. Retrying with a short backoff clears most of these, since the
# per-minute window resets quickly. Only genuinely exhausted daily quotas
# will still fail after these retries.
_MAX_EMBED_RETRIES = 3
_EMBED_RETRY_BACKOFF = [2, 5, 10]  # seconds


def _embed_with_retry(**kwargs):
    """Wraps genai.embed_content with retry/backoff on 429 / 503."""
    last_err = None
    for attempt in range(_MAX_EMBED_RETRIES + 1):
        try:
            return genai.embed_content(**kwargs)
        except (ResourceExhausted, ServiceUnavailable) as e:
            last_err = e
            if attempt < _MAX_EMBED_RETRIES:
                wait = _EMBED_RETRY_BACKOFF[attempt]
                logger.warning(
                    "[Embedder] Gemini quota/availability error (attempt %d/%d), "
                    "retrying in %ds: %s",
                    attempt + 1, _MAX_EMBED_RETRIES + 1, wait, e,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "[Embedder] Gemini still failing after %d attempts, giving up: %s",
                    _MAX_EMBED_RETRIES + 1, e,
                )
    raise last_err


def get_model() -> str:
    """
    Kept for compatibility with main.py's startup check. Makes one real
    API call so a bad/missing GEMINI_API_KEY fails loudly at boot instead
    of silently on the user's first query.
    """
    logger.info("[Embedder] Verifying Gemini embedding API: %s", _EMBED_MODEL)
    result = _embed_with_retry(
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
    """
    Used for document ingestion. Batches texts into as few API calls as
    possible (Gemini allows up to 100 texts per call) instead of one call
    per chunk — calling once per chunk hit the free-tier rate limit (429)
    on documents with many chunks.
    """
    if not texts:
        return []

    vectors: list[list[float]] = []
    BATCH_SIZE = 100  # Gemini's per-request limit
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        result = _embed_with_retry(
            model=_EMBED_MODEL,
            content=batch,
            task_type="retrieval_document",
            output_dimensionality=settings.embedding_dim,
        )
        vectors.extend(result["embedding"])
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

    result = _embed_with_retry(
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
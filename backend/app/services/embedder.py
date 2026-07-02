"""
Embedder — singleton model + Redis-backed embedding cache.

Added: embed_query() now checks Redis before running the model.
Same question asked twice (even across different users/sessions) reuses
the cached vector instead of recomputing it. embed_batch() for ingestion
is untouched — caching bulk document chunks isn't useful, they're unique.
"""
import hashlib
import json

from sentence_transformers import SentenceTransformer
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis_client import get_redis

logger = get_logger(__name__)
_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("[Embedder] Loading model: %s", settings.embed_model)
        _model = SentenceTransformer(settings.embed_model)
        logger.info("[Embedder] Model loaded (dim=%d)", settings.embedding_dim)
    return _model


def embed_batch(texts: list[str]) -> list[list[float]]:
    return get_model().encode(texts, show_progress_bar=False).tolist()


def _embedding_cache_key(text: str) -> str:
    normalized = text.strip().lower()
    return "rag:embcache:" + hashlib.sha256(normalized.encode()).hexdigest()


async def embed_query(text: str) -> list[float]:
    """
    Async now (was sync) — checks Redis cache first. Fails open: if Redis
    is down, falls straight through to computing the embedding directly,
    same fail-open pattern as cache.py and redis_client.py.
    """
    cache_key = _embedding_cache_key(text)
    try:
        cached = await get_redis().get(cache_key)
        if cached:
            logger.debug("[Embedder] Cache HIT for query embedding")
            return json.loads(cached)
    except RedisError as e:
        logger.warning("[Embedder] Cache get failed (continuing): %s", e)

    vector = embed_batch([text])[0]

    try:
        await get_redis().setex(cache_key, settings.embedding_cache_ttl, json.dumps(vector))
    except RedisError as e:
        logger.warning("[Embedder] Cache set failed (non-fatal): %s", e)

    return vector


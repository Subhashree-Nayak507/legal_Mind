import hashlib
import json

import google.generativeai as genai
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis_client import get_redis

logger = get_logger(__name__)

genai.configure(api_key=settings.gemini_api_key)
_EMBED_MODEL = "models/gemini-embedding-001"  


def get_model() -> str:
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
        result = genai.embed_content(
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
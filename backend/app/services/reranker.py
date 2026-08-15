import asyncio
import json

from groq import Groq

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client = Groq(api_key=settings.groq_api_key)
_RERANK_MODEL = settings.groq_model_fallback  


def _rerank_sync(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    if not candidates:
        return []

    numbered = "\n".join(f"[{i}] {c['text'][:500]}" for i, c in enumerate(candidates))
    prompt = (
        f"Query: {query}\n\nCandidate passages:\n{numbered}\n\n"
        f"Return ONLY a JSON array of the {min(top_k, len(candidates))} most relevant "
        "passage indices, ordered most to least relevant, e.g. [2, 0, 5]. No other text."
    )

    response = _client.chat.completions.create(
        model=_RERANK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=100,
    )
    raw = response.choices[0].message.content.strip()

    try:
        indices = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[Reranker] Could not parse LLM ranking output (%s) — using original order", raw)
        indices = list(range(min(top_k, len(candidates))))

    result = []
    for rank, idx in enumerate(indices[:top_k]):
        if isinstance(idx, int) and 0 <= idx < len(candidates):
            doc = candidates[idx]
            score = 1.0 - (rank / max(len(indices), 1))  # simple descending score
            result.append({**doc, "rerank_score": float(score)})

    logger.info(
        "[Reranker] top_score=%.3f | bottom_score=%.3f | returned %d/%d",
        result[0]["rerank_score"] if result else 0,
        result[-1]["rerank_score"] if result else 0,
        len(result),
        len(candidates),
    )
    return result


async def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Async wrapper — reranking runs in thread pool, not on event loop."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_rerank_sync, query, candidates, top_k),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.error("[Reranker] Timed out after 30s")
        raise


def _load_model():
    """
    Kept for main.py's startup fail-fast check. Verifies the Groq key
    actually works with one tiny real call instead of loading any local
    model — fails loudly at boot if the key is bad/missing.
    """
    logger.info("[Reranker] Verifying Groq API: %s", _RERANK_MODEL)
    _client.chat.completions.create(
        model=_RERANK_MODEL,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=1,
    )
    logger.info("[Reranker] Groq API ready")
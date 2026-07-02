"""
Reranker — unchanged logic, added async wrapper + logging.

Original ran synchronously on the event loop (blocking).
Now wrapped in asyncio.to_thread() — same fix as the LLM service.

Why this matters: reranker runs a neural model (cross-encoder) on CPU.
It takes 50-200ms depending on candidate count. Running that synchronously
freezes FastAPI from handling any other request during that time.
"""
import asyncio
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_tokenizer = None
_model = None


def _load_model():
    global _tokenizer, _model
    if _model is None:
        name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        logger.info("[Reranker] Loading: %s", name)
        _tokenizer = AutoTokenizer.from_pretrained(name)
        _model = AutoModelForSequenceClassification.from_pretrained(name)
        _model.eval()
        logger.info("[Reranker] Loaded")


def _rerank_sync(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Sync reranking — runs in thread pool via asyncio.to_thread()."""
    _load_model()
    if not candidates:
        return []

    pairs = [[query, c["text"]] for c in candidates]
    inputs = _tokenizer(
        pairs, padding=True, truncation=True, max_length=512, return_tensors="pt"
    )
    with torch.no_grad():
        logits = _model(**inputs).logits.squeeze(-1)
        scores = torch.sigmoid(logits).tolist()

    if isinstance(scores, float):
        scores = [scores]
        
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    result = [{**doc, "rerank_score": float(score)} for score, doc in ranked[:top_k]]

    logger.info(
        "[Reranker] top_score=%.3f | bottom_score=%.3f | returned %d/%d",
        result[0]["rerank_score"] if result else 0,
        result[-1]["rerank_score"] if result else 0,
        len(result),
        len(candidates),
    )
    return result


async def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Async wrapper — reranking runs in thread pool, not on event loop.

    Wrapped in a timeout: if the cross-encoder model isn't loaded yet
    (e.g. cold start) and the HF Hub download stalls, this raises instead
    of hanging the request forever — same fix as the LLM service's
    asyncio.wait_for pattern.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_rerank_sync, query, candidates, top_k),
            timeout=60,
        )
    except asyncio.TimeoutError:
        logger.error("[Reranker] Timed out after 60s — model load or inference stuck")
        raise

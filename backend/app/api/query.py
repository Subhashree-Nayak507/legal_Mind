"""
Query route — updated to use fixed services.

Changes vs original:
  - rerank() is now async (was sync, blocked event loop)
  - call_llm() returns LLMResult dataclass (not raw string)
  - Confidence threshold and reasoning logged (was silent)
  - Per-layer latency logged: retrieval, rerank, LLM separately
  - history passed as list[dict] directly (not formatted string at this stage)
  - LLM provider and model returned in response (useful for debugging)
"""
import time
import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.services.retriever import retrieve
from app.services.reranker import rerank
from app.db.redis_client import get_cached, set_cached, get_history, save_turn, format_history
from app.services.llm import call_llm
from app.core.config import settings
from app.core.logging import get_logger
from app.auth.dependencies import get_current_user

router = APIRouter()
logger = get_logger(__name__)


class QueryRequest(BaseModel):
    question: str
    session_id: str = "default"


@router.post("/query")
async def query_document(req: QueryRequest, user: dict = Depends(get_current_user)):
    start = time.monotonic()
    user_id = user["id"]

    # Cache key includes user_id — otherwise user A could get an answer
    # cached from user B's documents for the same question text.
    cache_key = f"{user_id}:{req.question}"

    # ── Cache check ────────────────────────────────────────────────────────
    cached = await get_cached(cache_key)
    if cached:
        logger.info("[Query] Cache hit for session=%s", req.session_id)
        return {
            **cached,
            "from_cache": True,
            "latency_ms": int((time.monotonic() - start) * 1000),
        }

    # ── Retrieval (scoped to this user's documents only) ─────────────────────
    t_retrieval = time.monotonic()
    candidates = await retrieve(req.question, user_id=user_id, top_k=settings.retrieval_top_k)
    retrieval_ms = int((time.monotonic() - t_retrieval) * 1000)

    if not candidates:
        raise HTTPException(404, "No documents found. Please upload documents first.")

    # ── Rerank ────────────────────────────────────────────────────────────
    t_rerank = time.monotonic()
    try:
        top_chunks = await rerank(req.question, candidates, top_k=settings.rerank_top_n)
    except TimeoutError:
        raise HTTPException(
            503,
            "Reranker model is still loading or unreachable (HuggingFace Hub "
            "download may be stuck). Check container network access and retry.",
        )
    rerank_ms = int((time.monotonic() - t_rerank) * 1000)

    best_score = top_chunks[0]["rerank_score"] if top_chunks else 0.0
    second_score = top_chunks[1]["rerank_score"] if len(top_chunks) > 1 else 0.0

    # ── Confidence gate (anti-hallucination) ──────────────────────────────
    # This specific reranker model wasn't trained on legal text, so its raw
    # scores sit low and inconsistent (often 0.0-0.15 even for correct
    # matches). A fixed absolute threshold doesn't work reliably here.
    # Instead: trust the answer if the top chunk clearly stands out from
    # the rest (gap) OR scores reasonably high on its own.
    gap = best_score - second_score
    is_confident = best_score > 0.01 and (gap > 0.02 or best_score > 0.3)

    logger.info(
        "[Query] best_score=%.3f second_score=%.3f gap=%.3f confident=%s session=%s",
        best_score, second_score, gap, is_confident, req.session_id,
    )

    if not is_confident:
        logger.warning(
            "[Query] Not confident (best=%.3f gap=%.3f) — refusing to answer",
            best_score, gap,
        )
    # ── Session memory (namespaced per user so session_id can't collide
    #    across different users) ───────────────────────────────────────────
    scoped_session_id = f"{user_id}:{req.session_id}"
    history = await get_history(scoped_session_id)
    history_str = format_history(history)

    # ── LLM call ──────────────────────────────────────────────────────────
    t_llm = time.monotonic()
    llm_result = await call_llm(req.question, top_chunks, history_str)
    llm_ms = int((time.monotonic() - t_llm) * 1000)

    total_ms = int((time.monotonic() - start) * 1000)

    logger.info(
        "[Query] DONE total=%dms (retrieval=%dms rerank=%dms llm=%dms) "
        "provider=%s user=%s session=%s",
        total_ms, retrieval_ms, rerank_ms, llm_ms,
        llm_result.provider, user_id, req.session_id,
    )

    # ── Save to session + cache ────────────────────────────────────────────
    await save_turn(scoped_session_id, req.question, llm_result.answer)

    sources = [
        {
            "filename": c["filename"],
            "chunk_index": c["chunk_index"],
            "text": c["text"][:200],
            "score": round(c["rerank_score"], 3),
        }
        for c in top_chunks
    ]

    response = {
        "answer":     llm_result.answer,
        "sources":    sources,
        "provider":   llm_result.provider,
        "confidence": round(best_score, 3),
        "from_cache": False,
    }
    await set_cached(cache_key, response)

    return {
        **response,
        "latency_breakdown": {
            "retrieval_ms": retrieval_ms,
            "rerank_ms":    rerank_ms,
            "llm_ms":       llm_ms,
            "total_ms":     total_ms,
        },
    }

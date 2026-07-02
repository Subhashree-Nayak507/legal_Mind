"""
LLM Service — fixed version.

Fixes applied vs original:
  FIX 1 — Singleton clients: Groq() and Gemini model created ONCE at module
           load, not per request. Creating a new HTTP client per request wastes
           connection pool, adds ~50ms overhead, leaks sockets.

  FIX 2 — Async LLM calls: Original used sync Groq client inside async route,
           which blocked FastAPI's event loop. Every request froze the entire
           server until the LLM responded. Now wrapped in asyncio.to_thread()
           so the event loop stays free for other requests during LLM wait.

  FIX 3 — Retry logic: Added exponential backoff (1s, 2s) before failing over.
           Rate limit errors skip retries and jump to next provider immediately.

  FIX 4 — Structured logging: Every provider attempt logged with latency.
           Interviewers ask "how do you debug slow queries" — you point here.


"""
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from groq import Groq, RateLimitError as GroqRateLimit
import google.generativeai as genai

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── FIX 1: Singletons created once at import time ─────────────────────────────
_groq_client = Groq(api_key=settings.groq_api_key)

genai.configure(api_key=settings.gemini_api_key)
_gemini_model = genai.GenerativeModel(settings.gemini_model)
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a precise and helpful legal document assistant.
Answer ONLY from the provided context chunks.
Never guess, invent, or hallucinate information.
If the context does not support the answer, say exactly:
"I don't have enough information in the uploaded documents to answer this."
Be clear and concise. Cite the source document and clause when relevant."""


@dataclass
class LLMResult:
    answer: str
    provider: str
    model: str
    latency_ms: int


def _build_prompt(query: str, chunks: list[dict], history: str) -> str:
    context_parts = []
    for c in chunks:
        # Use parent_text when available — it contains the full legal clause
        text = c.get("parent_text") or c["text"]
        context_parts.append(
            f"[Source: {c['filename']} | chunk {c['chunk_index']}]\n{text}"
        )
    context = "\n\n---\n\n".join(context_parts)
    history_block = f"CONVERSATION HISTORY:\n{history}\n\n" if history else ""
    return (
        f"{history_block}"
        f"CONTEXT FROM DOCUMENTS:\n{context}\n\n"
        f"USER QUESTION: {query}\n\n"
        "Answer clearly and cite the document/clause that supports your answer."
    )


def _call_groq_sync(messages: list[dict], model: str) -> str:
    """Sync Groq call — runs inside asyncio.to_thread() so it doesn't block."""
    response = _groq_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        max_tokens=800,
    )
    return response.choices[0].message.content


def _call_gemini_sync(prompt: str) -> str:
    """Sync Gemini call — runs inside asyncio.to_thread()."""
    result = _gemini_model.generate_content(
        f"{SYSTEM_PROMPT}\n\n{prompt}",
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=800,
        ),
    )
    return result.text


async def call_llm(query: str, chunks: list[dict], history: str) -> LLMResult:
    """
    Try providers in order. Return first success.
    Never raises — always returns a LLMResult (answer may be error message).
    """
    prompt = _build_prompt(query, chunks, history)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    # ── Provider 1: Groq primary ───────────────────────────────────────────
    result = await _try_groq(messages, settings.groq_model_primary, "groq-primary")
    if result:
        return result

    # ── Provider 2: Groq fallback ──────────────────────────────────────────
    result = await _try_groq(messages, settings.groq_model_fallback, "groq-fallback")
    if result:
        return result

    # ── Provider 3: Gemini ─────────────────────────────────────────────────
    result = await _try_gemini(prompt)
    if result:
        return result

    # All failed
    logger.error("[LLM] All providers failed for query: %s", query[:80])
    return LLMResult(
        answer="I'm temporarily unavailable. Please try again in a moment.",
        provider="none",
        model="none",
        latency_ms=0,
    )


async def _try_groq(
    messages: list[dict], model: str, label: str
) -> Optional[LLMResult]:
    for attempt in range(settings.llm_max_retries + 1):
        start = time.monotonic()
        try:
            # FIX 2: asyncio.to_thread() — sync Groq SDK runs in thread pool,
            # never blocks the event loop
            answer = await asyncio.wait_for(
                asyncio.to_thread(_call_groq_sync, messages, model),
                timeout=settings.llm_timeout,
            )
            latency = int((time.monotonic() - start) * 1000)
            logger.info("[LLM] %s responded in %dms", label, latency)
            return LLMResult(answer=answer, provider=label, model=model, latency_ms=latency)

        except asyncio.TimeoutError:
            logger.warning("[LLM] %s timeout after %ds", label, settings.llm_timeout)
            return None  # timeout = don't retry, move to next provider

        except GroqRateLimit:
            logger.warning("[LLM] %s rate limited — skipping to next provider", label)
            return None  # rate limit = don't retry, move to next provider

        except Exception as e:
            if attempt < settings.llm_max_retries:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning("[LLM] %s attempt %d failed (%s), retrying in %ds",
                               label, attempt + 1, e, wait)
                await asyncio.sleep(wait)
            else:
                logger.warning("[LLM] %s failed after %d attempts: %s",
                               label, settings.llm_max_retries + 1, e)
                return None


async def _try_gemini(prompt: str) -> Optional[LLMResult]:
    start = time.monotonic()
    try:
        answer = await asyncio.wait_for(
            asyncio.to_thread(_call_gemini_sync, prompt),
            timeout=settings.llm_timeout + 2,  # slightly longer for Gemini
        )
        latency = int((time.monotonic() - start) * 1000)
        logger.info("[LLM] gemini responded in %dms", latency)
        return LLMResult(
            answer=answer,
            provider="gemini",
            model=settings.gemini_model,
            latency_ms=latency,
        )
    except Exception as e:
        logger.error("[LLM] Gemini also failed: %s", e)
        return None

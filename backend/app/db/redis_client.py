"""
Central Redis client.

Three jobs:
  1. Query cache       — same question answered from cache, skips LLM entirely
  2. Session memory    — per-session chat history, trimmed to last N turns
  3. Rate limiting     — sliding window counter per IP stored in Redis
                         (NOT in-memory — survives restarts, works across workers)

All methods fail open: if Redis is down, requests are allowed through.
Cache misses on Redis failure are non-fatal — app degrades gracefully.
"""
import hashlib
import json
import time
from typing import Optional

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis: Optional[Redis] = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


# ── Query Cache ────────────────────────────────────────────────────────────────

def _cache_key(query: str) -> str:
    normalized = query.strip().lower()
    return "rag:cache:" + hashlib.sha256(normalized.encode()).hexdigest()


async def get_cached(query: str) -> Optional[dict]:
    try:
        val = await get_redis().get(_cache_key(query))
        if val:
            logger.debug(f"Cache HIT: {query[:60]}")
            return json.loads(val)
        return None
    except RedisError as e:
        logger.warning(f"Cache get failed (non-fatal): {e}")
        return None


async def set_cached(query: str, response: dict) -> None:
    try:
        await get_redis().setex(
            _cache_key(query), settings.cache_ttl, json.dumps(response)
        )
    except RedisError as e:
        logger.warning(f"Cache set failed (non-fatal): {e}")


# ── Session Memory ─────────────────────────────────────────────────────────────

def _session_key(session_id: str) -> str:
    return f"rag:session:{session_id}"


async def get_history(session_id: str, max_turns: int = 10) -> list[dict]:
    try:
        val = await get_redis().get(_session_key(session_id))
        history = json.loads(val) if val else []
        # Each turn = 2 messages (user + assistant), keep last N turns
        return history[-(max_turns * 2):]
    except RedisError as e:
        logger.warning(f"Session get failed (non-fatal): {e}")
        return []


async def save_turn(session_id: str, user_msg: str, assistant_msg: str) -> None:
    try:
        history = await get_history(session_id, max_turns=20)
        history.extend([
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ])
        await get_redis().setex(
            _session_key(session_id), settings.session_ttl, json.dumps(history)
        )
    except RedisError as e:
        logger.warning(f"Session save failed (non-fatal): {e}")


def format_history(history: list[dict]) -> str:
    if not history:
        return ""
    return "\n".join(
        f"{'USER' if m['role'] == 'user' else 'ASSISTANT'}: {m['content']}"
        for m in history
    )

async def check_rate_limit(identifier: str, limit: int, window: int = 60) -> tuple[bool, int]:
    """
    Simple fixed-window rate limiter using a Redis counter.
 
    How it works:
      - Each identifier (e.g. an IP) gets one counter key in Redis.
      - INCR increases the count by 1 on every request.
      - First request in a window: set the key to expire after `window` seconds.
      - After `window` seconds Redis deletes the key automatically → count resets to 0.
      - If count goes above `limit`, block the request.
 
    Easy to explain: "X requests allowed per minute, then it resets."
 
    Returns:
        (allowed: bool, remaining_requests: int)
    """
    try:
        key = f"rag:ratelimit:{identifier}"
        redis = get_redis()
 
        current_count = await redis.incr(key)
        if current_count == 1:
            # First request in this window — start the countdown
            await redis.expire(key, window)
 
        if current_count > limit:
            return False, 0
        return True, max(0, limit - current_count)
 
    except RedisError as e:
        # Fail open: if Redis is down, don't block users
        logger.warning(f"Rate limit check failed (allowing): {e}")
        return True, limit
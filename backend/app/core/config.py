from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM ───────────────────────────────────────────────────────────────
    groq_api_key: str = ""
    gemini_api_key: str = ""
    groq_model_primary: str = "llama-3.3-70b-versatile"
    groq_model_fallback: str = "llama-3.1-8b-instant"
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout: int = 8          # seconds before trying next provider
    llm_max_retries: int = 2      # retries per provider before giving up

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = ""

    # ── Redis ──────────────────────────────────────────────────────────────
    redis_url: str = ""
    cache_ttl: int = 3600         # query answer cache — 1 hour
    session_ttl: int = 86400      # chat history — 24 hours
    rate_limit_ttl: int = 60      # sliding window — 1 minute
    embedding_cache_ttl: int = 604800  # query embedding cache — 7 days (text→vector is stable)

    # ── Auth (JWT) ────────────────────────────────────────────────────────
    jwt_secret: str = ""   # override via .env, never commit a real one
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440   # 24 hours

    # ── Embedding ──────────────────────────────────────────────────────────
    embed_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # ── Chunking (tuned for legal docs) ───────────────────────────────────
    parent_chunk_size: int = 2000  # large: captures full legal clauses/sections
    child_chunk_size: int = 300    # small: precise vector search targets
    chunk_overlap: int = 50        # overlap prevents cutting mid-sentence

    # ── Retrieval ──────────────────────────────────────────────────────────
    retrieval_top_k: int = 20      # candidates from hybrid search
    rerank_top_n: int = 5          # final chunks sent to LLM
    confidence_threshold: float = 0.5  # below this → refuse to answer

    # ── Rate limiting ──────────────────────────────────────────────────────
    rate_limit_query: int = 20     # requests/minute per IP on /query
    rate_limit_ingest: int = 5     # uploads/minute per IP on /ingest
    rate_limit_global: int = 200   # total requests/minute across all users

    # ── File upload ────────────────────────────────────────────────────────
    max_file_size_mb: int = 10
    app_env: str = "development"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

"""
Structured logging.
Development: human-readable colored output.
Production: JSON lines — ingestible by any log aggregator (Datadog, CloudWatch).

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("Query answered", extra={"latency_ms": 142, "provider": "groq-primary"})
"""
import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    level = logging.DEBUG if settings.app_env == "development" else logging.INFO

    if settings.app_env == "production":
        fmt = (
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"module":"%(name)s","msg":"%(message)s"}'
        )
    else:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"

    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    # Suppress noisy third-party libs
    for lib in ["httpx", "httpcore", "asyncpg", "sentence_transformers", "transformers"]:
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

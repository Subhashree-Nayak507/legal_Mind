"""
Rate limiting middleware — simple per-IP fixed window.

Every IP gets X requests per minute per route.
Counter lives in Redis so it works across restarts.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis_client import check_rate_limit

logger = get_logger(__name__)

# How many requests per minute each route allows per IP
ROUTE_LIMITS = {
    "/api/v1/query":  settings.rate_limit_query,   # default 20/min
    "/api/v1/ingest": settings.rate_limit_ingest,  # default 5/min
}


class RateLimitMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only rate limit API routes
        if not path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Check limit for this route
        for route, limit in ROUTE_LIMITS.items():
            if path.startswith(route):
                allowed, remaining = await check_rate_limit(
                    f"{route}:{client_ip}", limit
                )
                if not allowed:
                    logger.warning("[RateLimit] %s blocked %s", route, client_ip)
                    return JSONResponse(
                        status_code=429,
                        content={"error": "Too many requests. Try again in a minute."},
                        headers={"Retry-After": "60"},
                    )
                response = await call_next(request)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                return response

        return await call_next(request)
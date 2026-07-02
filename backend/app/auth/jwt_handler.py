"""
JWT handler — token creation/verification + password hashing.

Why these choices:
  - passlib[bcrypt] for hashing — industry standard, salts automatically,
    slow-by-design (resists brute force) unlike a fast hash like SHA256.
  - python-jose for JWT — encode/decode + signature verification.
  - HS256 (symmetric secret) — simpler than RS256 for a single-backend
    portfolio project. RS256 only matters once multiple services need to
    verify tokens independently.

Interview answer ready: "Why JWT over sessions?" → JWT is stateless, the
token itself carries the user identity, so the API can verify it without
a DB round-trip on every request. Session lookups would need Redis/DB hit
each time; JWT only needs DB lookups when you need fresh user data.
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password hashing ────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


# ── JWT creation/verification ───────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> tuple[str, int]:
    """
    Returns (token, expires_in_seconds).
    Payload kept minimal — sub (user id) and email only. Never put
    passwords or sensitive data in a JWT payload; it's base64, not encrypted.
    """
    expire_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expire_delta

    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire_at,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(expire_delta.total_seconds())


def decode_access_token(token: str) -> Optional[dict]:
    """Returns payload dict if valid, None if invalid/expired."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.warning("[Auth] Token decode failed: %s", e)
        return None

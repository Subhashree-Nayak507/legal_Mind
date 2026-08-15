import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, email: str) -> tuple[str, int]:
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

    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.warning("[Auth] Token decode failed: %s", e)
        return None

"""
Auth routes — register + login. JWT-only, no OAuth.

POST /api/v1/auth/register  → creates user, returns token (auto-login)
POST /api/v1/auth/login     → verifies password, returns token
"""
from fastapi import APIRouter, HTTPException, status

from app.auth.schemas import RegisterRequest, LoginRequest, TokenResponse
from app.auth.jwt_handler import hash_password, verify_password, create_access_token
from app.db.postgres import create_user, get_user_by_email
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    existing = await get_user_by_email(req.email)
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    hashed = hash_password(req.password)
    user = await create_user(email=req.email, hashed_password=hashed, name=req.name)

    token, expires_in = create_access_token(user_id=user["id"], email=user["email"])
    logger.info("[Auth] New user registered: %s", req.email)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = await get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["hashed_password"]):
        # Same error for "no such user" and "wrong password" —
        # don't leak which one it was, that's an enumeration risk.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    token, expires_in = create_access_token(user_id=user["id"], email=user["email"])
    logger.info("[Auth] Login: %s", req.email)
    return TokenResponse(access_token=token, expires_in=expires_in)

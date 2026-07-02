"""
FastAPI dependency — extracts + validates the current user from the
Authorization: Bearer <token> header.

Use as: async def route(user: dict = Depends(get_current_user))
Adding it to a route is the entire auth check — FastAPI runs this before
the route body executes, and raises 401 automatically if it fails.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.auth.jwt_handler import decode_access_token

# tokenUrl is just where Swagger's "Authorize" button looks for a login
# endpoint — does not mean OAuth is used anywhere in this flow.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"id": payload["sub"], "email": payload["email"]}

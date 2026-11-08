"""Login, signed tokens (JWT) and the three access levels: guest, user, admin."""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger("lawliet.auth")

bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"

# Compared against when the username does not exist, so both failure paths take similar time.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret or len(secret) < 32:
        log.error("JWT_SECRET is missing or shorter than 32 characters")
        raise HTTPException(status_code=500, detail="Something went wrong.")
    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: Optional[str]) -> bool:
    stored = password_hash.encode() if password_hash else _DUMMY_HASH
    ok = bcrypt.checkpw(password.encode(), stored)
    return ok and password_hash is not None


def create_token(user: dict) -> str:
    minutes = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def optional_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> Optional[dict]:
    """No token -> None (guest). A token that is present but invalid or expired -> 401."""
    if creds is None:
        return None
    try:
        claims = jwt.decode(
            creds.credentials, _secret(), algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401, detail="Invalid or expired login.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"id": int(claims["sub"]), "username": claims.get("username"), "role": claims["role"]}


def require_user(user: Optional[dict] = Depends(optional_user)) -> dict:
    if user is None:
        raise HTTPException(
            status_code=401, detail="Log in to continue.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user

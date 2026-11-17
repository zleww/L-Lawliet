"""Login, signed tokens (JWT), Google sign-in and the three access levels: guest, user, admin."""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer

import _db as db

log = logging.getLogger("lawliet.auth")

# Two ways to send the same "Authorization: Bearer <token>" header. Both show in Swagger's
# Authorize dialog: OAuth2 asks for a username and password and fetches the token itself;
# HTTPBearer takes a pasted token (needed for Google accounts, which have no password).
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False,
                              scheme_name="Log in with username and password")
bearer = HTTPBearer(auto_error=False, scheme_name="Paste a token",
                    description="A token from POST /api/v1/auth/login or Google sign-in.")
ALGORITHM = "HS256"

# Compared against when the username does not exist, so both failure paths take similar time.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())

# Google publishes the keys that sign its ID tokens here. PyJWKClient caches them,
# so a warm serverless instance does not download them on every sign-in.
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_google_keys = jwt.PyJWKClient(GOOGLE_CERTS_URL, cache_keys=True, lifespan=3600)


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret or len(secret) < 32:
        log.error("JWT_SECRET is missing or shorter than 32 characters")
        raise HTTPException(status_code=500, detail="Something went wrong.")
    return secret


def google_client_id() -> Optional[str]:
    return os.environ.get("GOOGLE_CLIENT_ID") or None


# ----------------------------------------------------------------------
# Passwords
# ----------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, password_hash: Optional[str]) -> bool:
    """bcrypt only reads 72 bytes and bcrypt 5 raises on longer input, so a longer
    password is compared against the dummy hash and always fails."""
    raw = password.encode()
    stored = password_hash.encode() if password_hash else _DUMMY_HASH
    if len(raw) > 72:
        bcrypt.checkpw(b"x", _DUMMY_HASH)  # keep the timing similar
        return False
    ok = bcrypt.checkpw(raw, stored)
    return ok and password_hash is not None


# ----------------------------------------------------------------------
# Tokens
# ----------------------------------------------------------------------
def create_token(user: dict) -> str:
    minutes = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "ver": user.get("token_version", 0),  # raised by "log out of all devices" and password changes
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def optional_user(
    token: Optional[str] = Depends(oauth2),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    conn=Depends(db.get_db),
) -> Optional[dict]:
    """No token -> None (guest). A bad or expired token -> 401 without touching the database.
    A valid token is checked against the account: deleted accounts and tokens from before
    "log out of all devices" or a password change are refused. Role comes from the database,
    not from the token."""
    raw = token or (creds.credentials if creds else None)
    if not raw:
        return None
    try:
        claims = jwt.decode(
            raw, _secret(), algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "role"]},
        )
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        raise _unauthorized("Invalid or expired login.")

    account = db.get_user_by_id(conn, user_id)
    if account is None or account["token_version"] != claims.get("ver", 0):
        raise _unauthorized("Your login is no longer valid. Please log in again.")
    return account


def require_user(user: Optional[dict] = Depends(optional_user)) -> dict:
    if user is None:
        raise _unauthorized("Log in to continue.")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


# ----------------------------------------------------------------------
# Google sign-in
# ----------------------------------------------------------------------
def verify_google_credential(credential: str) -> dict:
    """Checks the ID token from Google's button: Google's signature, that it was issued
    for this site's client ID, the issuer, expiry, and that Google verified the email."""
    client_id = google_client_id()
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not set up.")
    try:
        key = _google_keys.get_signing_key_from_jwt(credential)
    except jwt.PyJWKClientConnectionError:
        log.exception("Could not download Google's signing keys")
        raise HTTPException(status_code=503, detail="Google sign-in is temporarily unavailable.")
    except jwt.PyJWTError:
        raise _unauthorized("Google sign-in failed.")
    try:
        claims = jwt.decode(
            credential, key.key, algorithms=["RS256"], audience=client_id,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=30,
        )
    except jwt.PyJWTError:
        raise _unauthorized("Google sign-in failed.")
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise _unauthorized("Google sign-in failed.")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise _unauthorized("Your Google account's email is not verified.")
    return claims

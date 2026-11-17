"""L-Lawliet API: Philippine Republic Acts in plain English, stored in Neon PostgreSQL.

Routes only: each handler checks access, lets Pydantic validate input, calls one
query function in _db.py and returns JSON. Secrets come from environment variables.
"""
import logging
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # lets Vercel and uvicorn find the helpers

try:  # local development only; Vercel provides real environment variables
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2
from psycopg2 import errors as pg_errors
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse

import _db as db
from _auth import (
    check_password, create_token, google_client_id, hash_password, optional_user,
    require_admin, require_user, verify_google_credential,
)
from _models import (
    Category, CommentEdit, CommentSubmission, DeleteAccountRequest, GoogleLoginRequest,
    LawCreate, LawUpdate, LoginRequest, PasswordChange, ProfileUpdate, RegisterRequest,
)

API_VERSION = "2.1"
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lawliet.api")

app = FastAPI(
    title="L-Lawliet API",
    description="Simplified Philippine Republic Acts, backed by Neon PostgreSQL.",
    version=API_VERSION,
    docs_url="/api/docs",            # Vercel only routes /api/*, so the docs live there
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

allowed_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,  # tokens travel in the Authorization header, not cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    # X-API-Key is still accepted in CORS only because JurisCard and JustGiveupATP send it;
    # the API ignores its value, so those sites are treated as guests.
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


# ==========================================================
# ERROR HANDLING: database errors become short, safe messages
# ==========================================================
@app.exception_handler(psycopg2.Error)
def database_error(request: Request, exc: psycopg2.Error):
    if isinstance(exc, pg_errors.UniqueViolation):
        if exc.diag.table_name == "users":
            return JSONResponse(status_code=409, content={"detail": "That username or account already exists."})
        return JSONResponse(status_code=409, content={"detail": "A law with this RA number already exists."})
    if isinstance(exc, pg_errors.InsufficientPrivilege):
        # A database security rule (RLS policy or column privilege) refused the change.
        log.warning("Database refused a write: %s", exc.pgerror)
        return JSONResponse(status_code=403, content={"detail": "You are not allowed to do that."})
    if isinstance(exc, pg_errors.ForeignKeyViolation):
        return JSONResponse(status_code=404, content={"detail": "Law not found."})
    if isinstance(exc, (pg_errors.CheckViolation, pg_errors.NotNullViolation, pg_errors.StringDataRightTruncation)):
        return JSONResponse(status_code=422, content={"detail": "A value breaks a database rule."})
    if isinstance(exc, psycopg2.OperationalError):
        log.exception("Database unavailable")
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable."})
    log.exception("Database query failed")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong."})


@app.exception_handler(Exception)
def unexpected_error(request: Request, exc: Exception):
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong."})


def access_level(user: Optional[dict]) -> str:
    return "full" if user else "guest"


def access_info(user: Optional[dict]) -> dict:
    info = {"access": access_level(user)}
    if user is None:
        info["guest_limit"] = db.GUEST_PREVIEW_SIZE
    return info


# ==========================================================
# HEALTH CHECK (Public)
# ==========================================================
@app.get("/api/health", tags=["System"])
def health_check(conn=Depends(db.get_db)):
    db.ping(conn)
    return {
        "status": "ok",
        "database": "connected",
        "service": "L-Lawliet API",
        "version": API_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ==========================================================
# ACCOUNTS: sign up, log in, Google sign-in (Public)
# ==========================================================
def public_profile(account: dict) -> dict:
    """The account fields a browser may see (no password hash, no Google id)."""
    return {
        "id": account["id"],
        "username": account["username"],
        "role": account["role"],
        "email": account.get("email"),
        "display_name": account.get("display_name"),
        "bio": account.get("bio"),
        "theme": account.get("theme", "dark"),
        "accent": account.get("accent", "gold"),
        "has_password": account.get("has_password", True),
        "google_linked": account.get("google_linked", False),
        "created_at": account.get("created_at"),
    }


def session_response(account: dict) -> dict:
    """Login result. token, username and role stay at the top level for older clients."""
    return {
        "token": create_token(account),
        "username": account["username"],
        "role": account["role"],
        "user": public_profile(account),
    }


@app.get("/api/v1/auth/config", tags=["Auth"])
def auth_config():
    """Public settings the login page needs. The Google client ID is not a secret."""
    return {"google_client_id": google_client_id()}


@app.post("/api/v1/auth/register", status_code=201, tags=["Auth"])
def register(payload: RegisterRequest, conn=Depends(db.get_db)):
    if db.username_taken(conn, payload.username):
        raise HTTPException(status_code=409, detail="That username is already taken.")
    account = db.create_user(
        conn, username=payload.username, password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    return session_response(account)


def password_login(conn, username: str, password: str) -> dict:
    """Shared by the JSON login and Swagger's Authorize form. Lockout after 5 wrong passwords."""
    found = db.get_user_by_username(conn, username)
    if found and found["is_locked"]:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {found['minutes_left']} minute(s).",
        )
    if not check_password(password, found["password_hash"] if found else None):
        if found:
            db.record_failed_login(conn, found)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if found["failed_logins"] or found["locked_until"]:
        db.clear_failed_logins(conn, found)
    return db.get_user_by_id(conn, found["id"])


@app.post("/api/v1/auth/login", tags=["Auth"])
def login(payload: LoginRequest, conn=Depends(db.get_db)):
    return session_response(password_login(conn, payload.username, payload.password))


@app.post("/api/v1/auth/token", tags=["Auth"])
def login_form(form: OAuth2PasswordRequestForm = Depends(), conn=Depends(db.get_db)):
    """Used by Swagger's Authorize button (OAuth2 password flow, form fields username and
    password). Same accounts, rules and lockout as /api/v1/auth/login."""
    username, password = form.username.strip(), form.password
    if not 1 <= len(username) <= 50 or not 1 <= len(password) <= 200:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    account = password_login(conn, username, password)
    return {"access_token": create_token(account), "token_type": "bearer",
            "username": account["username"], "role": account["role"]}


def _username_from_email(conn, email: str) -> str:
    """juan.dela.cruz@gmail.com -> juan.dela.cruz (or juan.dela.cruz4821 if taken)."""
    base = re.sub(r"[^A-Za-z0-9_.]", "", email.split("@")[0])[:24] or "user"
    base = base.ljust(3, "0")
    candidate = base
    for _ in range(10):
        if not db.username_taken(conn, candidate):
            return candidate
        candidate = f"{base}{secrets.randbelow(10000):04d}"
    raise HTTPException(status_code=409, detail="Could not create a username. Please try again.")


@app.post("/api/v1/auth/google", tags=["Auth"])
def google_login(payload: GoogleLoginRequest, conn=Depends(db.get_db)):
    """Sign in with Google. The first sign-in creates an ordinary user account."""
    claims = verify_google_credential(payload.credential)
    account = db.get_user_by_google_sub(conn, claims["sub"])
    if account is None:
        name = (claims.get("name") or "").strip()[:100] or None
        account = db.create_user(
            conn, username=_username_from_email(conn, claims["email"]), display_name=name,
            email=claims["email"].lower(), google_sub=claims["sub"],
        )
    return session_response(account)


# ==========================================================
# MY ACCOUNT: profile, password, sessions, delete (User or admin)
# ==========================================================
@app.get("/api/v1/me", tags=["Account"])
def get_me(user: dict = Depends(require_user)):
    return public_profile(user)


@app.patch("/api/v1/me", tags=["Account"])
def update_me(payload: ProfileUpdate, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    return public_profile(db.update_profile(conn, user, payload.model_dump(exclude_unset=True)))


@app.post("/api/v1/me/password", tags=["Account"])
def change_password(payload: PasswordChange, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    """Signs out every other device and returns a fresh token for this one."""
    if not user["has_password"]:
        raise HTTPException(status_code=400, detail="This account signs in with Google and has no password.")
    if not check_password(payload.current_password, db.get_password_hash(conn, user["id"])):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if payload.new_password.lower() == user["username"].lower():
        raise HTTPException(status_code=422, detail="Password cannot be the same as the username.")
    return session_response(db.set_password(conn, user, hash_password(payload.new_password)))


@app.post("/api/v1/auth/logout-all", status_code=204, tags=["Account"])
def logout_all(user: dict = Depends(require_user), conn=Depends(db.get_db)):
    """Every login token for this account stops working, on every device."""
    db.bump_token_version(conn, user)
    return Response(status_code=204)


@app.delete("/api/v1/me", status_code=204, tags=["Account"])
def delete_me(payload: DeleteAccountRequest, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    """Deletes the account. Its notes stay on the laws, shown as 'Deleted user'."""
    if payload.confirm.strip().lower() != user["username"].lower():
        raise HTTPException(status_code=400, detail="Type your username exactly to confirm.")
    if user["has_password"] and not check_password(payload.password or "", db.get_password_hash(conn, user["id"])):
        raise HTTPException(status_code=400, detail="Password is incorrect.")
    if user["role"] == "admin" and db.count_admins(conn) <= 1:
        raise HTTPException(status_code=409, detail="You are the only admin, so this account cannot be deleted.")
    db.delete_user(conn, user)
    return Response(status_code=204)


# ==========================================================
# STATS (Public): counts only, for the home page
# ==========================================================
@app.get("/api/v1/stats", tags=["Laws"])
def get_stats(conn=Depends(db.get_db)):
    return db.stats(conn)


# ==========================================================
# SEARCH LAWS (guest: first 10 only)
# ==========================================================
@app.get("/api/v1/laws/search", tags=["Laws"])
@app.get("/api/laws/search", include_in_schema=False)
def search_laws(
    q: str = Query(..., min_length=1, max_length=100, description="Keyword"),
    user: Optional[dict] = Depends(optional_user),
    conn=Depends(db.get_db),
):
    laws, total = db.list_laws(conn, guest=user is None, search=q.strip())
    return {"query": q, "count": len(laws), "total": total, **access_info(user), "results": laws}


# ==========================================================
# LIST LAWS (guest: first 10 only)
# ==========================================================
@app.get("/api/v1/laws", tags=["Laws"])
@app.get("/api/laws", include_in_schema=False)
def get_laws(
    category: Optional[Category] = None,
    search: Optional[str] = Query(default=None, max_length=100),
    user: Optional[dict] = Depends(optional_user),
    conn=Depends(db.get_db),
):
    laws, total = db.list_laws(
        conn, guest=user is None, category=category, search=(search or "").strip() or None
    )
    return {"count": len(laws), "total": total, **access_info(user), "laws": laws}


# ==========================================================
# GET ONE LAW (guest: first 10 only)
# ==========================================================
@app.get("/api/v1/laws/{law_id}", tags=["Laws"])
@app.get("/api/laws/{law_id}", include_in_schema=False)
def get_law(law_id: int, user: Optional[dict] = Depends(optional_user), conn=Depends(db.get_db)):
    law = db.get_law(conn, law_id)
    if law is None:
        raise HTTPException(status_code=404, detail="Law not found.")
    if user is None and not db.is_in_preview(conn, law_id):
        raise HTTPException(status_code=401, detail="Log in to view this law.")
    return law


# ==========================================================
# CREATE / UPDATE / DELETE A LAW (Admin)
# ==========================================================
@app.post("/api/v1/laws", status_code=201, tags=["Admin"])
def create_law(payload: LawCreate, admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    return db.create_law(conn, payload.model_dump(), admin)


@app.patch("/api/v1/laws/{law_id}", tags=["Admin"])
def update_law(law_id: int, payload: LawUpdate, admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    law = db.update_law(conn, law_id, payload.model_dump(exclude_unset=True), admin)
    if law is None:
        raise HTTPException(status_code=404, detail="Law not found.")
    return law


@app.delete("/api/v1/laws/{law_id}", status_code=204, tags=["Admin"])
def delete_law(law_id: int, admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    if not db.delete_law(conn, law_id, admin):
        raise HTTPException(status_code=404, detail="Law not found.")
    return Response(status_code=204)


# ==========================================================
# ADD COMMENT (User or admin)
# ==========================================================
@app.post("/api/v1/laws/{law_id}/comments", status_code=201, tags=["Comments"])
def add_user_comment(
    law_id: int, payload: CommentSubmission,
    user: dict = Depends(require_user), conn=Depends(db.get_db),
):
    comments = db.add_comment(conn, law_id, user, payload.user_name, payload.comment)
    return {"message": "Knowledge added successfully!", "comments": comments}


# ==========================================================
# EDIT MY COMMENT (the author only)
# ==========================================================
@app.patch("/api/v1/comments/{comment_id}", tags=["Comments"])
def edit_comment(
    comment_id: int, payload: CommentEdit,
    user: dict = Depends(require_user), conn=Depends(db.get_db),
):
    found = db.get_comment(conn, comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Note not found.")
    if found["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only edit your own notes.")
    comments = db.update_comment(conn, comment_id, user, payload.comment)
    if comments is None:  # the comments_update_own policy refused the row
        raise HTTPException(status_code=403, detail="You can only edit your own notes.")
    return {"message": "Note updated.", "comments": comments}


# ==========================================================
# DELETE A COMMENT (the author, or an admin)
# ==========================================================
@app.delete("/api/v1/comments/{comment_id}", status_code=204, tags=["Comments"])
def delete_comment(comment_id: int, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    found = db.get_comment(conn, comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Note not found.")
    if found["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="You can only delete your own notes.")
    if not db.delete_comment(conn, comment_id, user):  # the comments_delete_own policy refused it
        raise HTTPException(status_code=403, detail="You can only delete your own notes.")
    return Response(status_code=204)

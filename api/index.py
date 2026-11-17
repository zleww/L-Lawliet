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
from typing import Literal, Optional

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
    LawCreate, LawUpdate, LoginRequest, PasswordChange, ProfileUpdate, RatingRequest,
    RegisterRequest, ReportRequest, ReportReview, SuggestionCreate, SuggestionReview,
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
        duplicate = {
            "users": "That username or account already exists.",
            "saved_laws": "You already saved this law.",
            "comment_votes": "You already marked this note as helpful.",
            "comment_reports": "You already reported this note.",
            "law_suggestions": "You already have a pending suggestion for this RA number.",
        }.get(exc.diag.table_name, "A law with this RA number already exists.")
        return JSONResponse(status_code=409, content={"detail": duplicate})
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
    """Logged in: also says whether you saved the law, your rating, and the notes you marked helpful."""
    law = db.get_law(conn, law_id, user)
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


# ==========================================================
# SAVED LAWS (each user's private bookmarks)
# ==========================================================
@app.get("/api/v1/me/saved", tags=["Saved laws"])
def my_saved_laws(user: dict = Depends(require_user), conn=Depends(db.get_db)):
    saved = db.list_saved(conn, user)
    return {"count": len(saved), "saved": saved}


@app.post("/api/v1/laws/{law_id}/save", status_code=201, tags=["Saved laws"])
def save_law(law_id: int, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    row = db.save_law(conn, user, law_id)  # 409 if already saved, 404 if the law does not exist
    return {"law_id": law_id, "saved": True, "saved_at": row["saved_at"]}


@app.delete("/api/v1/laws/{law_id}/save", status_code=204, tags=["Saved laws"])
def unsave_law(law_id: int, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    if not db.unsave_law(conn, user, law_id):
        raise HTTPException(status_code=404, detail="This law is not in your saved laws.")
    return Response(status_code=204)


# ==========================================================
# RATINGS (one 1-5 rating per user per law)
# ==========================================================
@app.put("/api/v1/laws/{law_id}/rating", tags=["Ratings"])
def rate_law(law_id: int, payload: RatingRequest, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    """Rating again replaces your earlier rating."""
    if db.get_law(conn, law_id) is None:
        raise HTTPException(status_code=404, detail="Law not found.")
    return {"law_id": law_id, **db.set_rating(conn, user, law_id, payload.rating)}


@app.delete("/api/v1/laws/{law_id}/rating", status_code=204, tags=["Ratings"])
def remove_rating(law_id: int, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    if not db.delete_rating(conn, user, law_id):
        raise HTTPException(status_code=404, detail="You have not rated this law.")
    return Response(status_code=204)


# ==========================================================
# HELPFUL VOTES AND REPORTS ON NOTES
# ==========================================================
def _note_by_someone_else(conn, comment_id: int, user: dict, own_message: str) -> dict:
    found = db.get_comment(conn, comment_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Note not found.")
    if found["user_id"] == user["id"]:
        raise HTTPException(status_code=403, detail=own_message)
    return found


@app.post("/api/v1/comments/{comment_id}/vote", status_code=201, tags=["Comments"])
def vote_helpful(comment_id: int, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    _note_by_someone_else(conn, comment_id, user, "You can't mark your own note as helpful.")
    count = db.add_vote(conn, user, comment_id)  # 409 if you already voted
    return {"comment_id": comment_id, "voted": True, "helpful_count": count}


@app.delete("/api/v1/comments/{comment_id}/vote", status_code=204, tags=["Comments"])
def remove_vote(comment_id: int, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    if not db.remove_vote(conn, user, comment_id):
        raise HTTPException(status_code=404, detail="You have not marked this note as helpful.")
    return Response(status_code=204)


@app.post("/api/v1/comments/{comment_id}/report", status_code=201, tags=["Comments"])
def report_note(comment_id: int, payload: ReportRequest, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    """Reasons: spam, offensive, wrong_info, other. One report per user per note."""
    _note_by_someone_else(conn, comment_id, user, "You can't report your own note.")
    row = db.add_report(conn, user, comment_id, payload.reason, payload.details)  # 409 if already reported
    return {"message": "Thanks, an admin will review this note.", "report_id": row["id"], "status": row["status"]}


# ==========================================================
# LAW SUGGESTIONS (users suggest, admins review)
# ==========================================================
@app.post("/api/v1/suggestions", status_code=201, tags=["Suggestions"])
def suggest_law(payload: SuggestionCreate, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    """Short form: RA number, title, why it matters, optional https source. An admin adds the full law."""
    if db.law_id_by_ra(conn, payload.ra_number):
        raise HTTPException(status_code=409, detail=f"{payload.ra_number} is already in L-Lawliet.")
    return db.create_suggestion(conn, user, payload.model_dump())


@app.get("/api/v1/me/suggestions", tags=["Suggestions"])
def my_suggestions(user: dict = Depends(require_user), conn=Depends(db.get_db)):
    rows = db.list_my_suggestions(conn, user)
    return {"count": len(rows), "suggestions": rows}


# ==========================================================
# PUBLIC PROFILES (logged-in users only)
# ==========================================================
@app.get("/api/v1/users/{user_id}", tags=["Profiles"])
def get_profile(user_id: int, user: dict = Depends(require_user), conn=Depends(db.get_db)):
    """Display name, bio, member since and notes. Never email, settings or saved laws."""
    profile = db.get_profile(conn, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return profile


# ==========================================================
# ADMIN: moderation, suggestions and accounts
# ==========================================================
@app.get("/api/v1/admin/reports", tags=["Admin"])
def admin_reports(
    status: Literal["open", "dismissed"] = "open",
    admin: dict = Depends(require_admin), conn=Depends(db.get_db),
):
    rows = db.list_reports(conn, admin, status)
    return {"count": len(rows), "reports": rows}


@app.patch("/api/v1/admin/reports/{report_id}", tags=["Admin"])
def admin_resolve_report(
    report_id: int, payload: ReportReview, admin: dict = Depends(require_admin), conn=Depends(db.get_db),
):
    """Dismiss a report. To remove the note instead, DELETE /api/v1/comments/{comment_id}."""
    row = db.resolve_report(conn, admin, report_id, payload.status)
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return row


@app.get("/api/v1/admin/suggestions", tags=["Admin"])
def admin_suggestions(
    status: Literal["pending", "approved", "rejected"] = "pending",
    admin: dict = Depends(require_admin), conn=Depends(db.get_db),
):
    rows = db.list_suggestions(conn, admin, status)
    return {"count": len(rows), "suggestions": rows}


@app.patch("/api/v1/admin/suggestions/{suggestion_id}", tags=["Admin"])
def admin_review_suggestion(
    suggestion_id: int, payload: SuggestionReview, admin: dict = Depends(require_admin), conn=Depends(db.get_db),
):
    """Approve with the law_id of the law you created for it, or reject with an optional note."""
    current = db.get_suggestion_status(conn, admin, suggestion_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    if current != "pending":
        raise HTTPException(status_code=409, detail="This suggestion was already reviewed.")
    if payload.law_id is not None and db.get_law(conn, payload.law_id) is None:
        raise HTTPException(status_code=404, detail="Law not found.")
    row = db.review_suggestion(conn, admin, suggestion_id, payload.status, payload.admin_note, payload.law_id)
    if row is None:
        raise HTTPException(status_code=409, detail="This suggestion was already reviewed.")
    return row


@app.get("/api/v1/admin/users", tags=["Admin"])
def admin_users(admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    rows = db.list_users(conn)
    return {"count": len(rows), "users": rows}


@app.post("/api/v1/admin/users/{user_id}/unlock", tags=["Admin"])
def admin_unlock_user(user_id: int, admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    """Clear the 15-minute lockout after 5 wrong passwords."""
    if not db.admin_unlock(conn, admin, user_id):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user_id": user_id, "unlocked": True}


@app.post("/api/v1/admin/users/{user_id}/logout-all", status_code=204, tags=["Admin"])
def admin_logout_user(user_id: int, admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    """Every login token of that account stops working (e.g. a stolen login)."""
    if not db.bump_token_version(conn, admin, user_id):
        raise HTTPException(status_code=404, detail="User not found.")
    return Response(status_code=204)


@app.delete("/api/v1/admin/users/{user_id}", status_code=204, tags=["Admin"])
def admin_delete_user(user_id: int, admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    """Delete a non-admin account. Its notes stay, shown as 'Deleted user'."""
    role = db.get_user_role(conn, user_id)
    if role is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if role == "admin":
        raise HTTPException(status_code=403, detail="Admin accounts can't be deleted here.")
    if not db.delete_user(conn, admin, user_id):
        raise HTTPException(status_code=403, detail="You are not allowed to do that.")
    return Response(status_code=204)

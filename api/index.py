"""L-Lawliet API: Philippine Republic Acts in plain English, stored in Neon PostgreSQL.

Routes only: each handler checks access, lets Pydantic validate input, calls one
query function in _db.py and returns JSON. Secrets come from environment variables.
"""
import logging
import os
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
from fastapi.responses import JSONResponse

import _db as db
from _auth import check_password, create_token, optional_user, require_admin, require_user
from _models import Category, CommentSubmission, LawCreate, LawUpdate, LoginRequest

API_VERSION = "2.0"
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
    allow_headers=["Authorization", "Content-Type"],
)


# ==========================================================
# ERROR HANDLING: database errors become short, safe messages
# ==========================================================
@app.exception_handler(psycopg2.Error)
def database_error(request: Request, exc: psycopg2.Error):
    if isinstance(exc, pg_errors.UniqueViolation):
        return JSONResponse(status_code=409, content={"detail": "A law with this RA number already exists."})
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
# LOGIN (Public)
# ==========================================================
@app.post("/api/v1/auth/login", tags=["Auth"])
def login(payload: LoginRequest, conn=Depends(db.get_db)):
    user = db.get_user_by_username(conn, payload.username)
    if not check_password(payload.password, user["password_hash"] if user else None):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"token": create_token(user), "username": user["username"], "role": user["role"]}


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
    return {"query": q, "count": len(laws), "total": total, "access": access_level(user), "results": laws}


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
    return {"count": len(laws), "total": total, "access": access_level(user), "laws": laws}


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
    return db.create_law(conn, payload.model_dump())


@app.patch("/api/v1/laws/{law_id}", tags=["Admin"])
def update_law(law_id: int, payload: LawUpdate, admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    law = db.update_law(conn, law_id, payload.model_dump(exclude_unset=True))
    if law is None:
        raise HTTPException(status_code=404, detail="Law not found.")
    return law


@app.delete("/api/v1/laws/{law_id}", status_code=204, tags=["Admin"])
def delete_law(law_id: int, admin: dict = Depends(require_admin), conn=Depends(db.get_db)):
    if not db.delete_law(conn, law_id):
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
    comments = db.add_comment(conn, law_id, user["id"], payload.user_name, payload.comment)
    return {"message": "Knowledge added successfully!", "comments": comments}

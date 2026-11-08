"""Database access for L-Lawliet: the connection dependency and every SQL query.

All values are passed as %s parameters, never formatted into the SQL string.
Column names in UPDATE come only from LAW_COLUMNS, never from the request.
"""
import logging
import os

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import HTTPException

log = logging.getLogger("lawliet.db")

GUEST_PREVIEW_SIZE = 10

LAW_COLUMNS = (
    "ra_number", "official_title", "plain_title", "category", "year", "status",
    "reading_time_minutes", "importance_rating", "tldr_summary", "full_breakdown",
    "why_it_matters", "example_scenario", "penalties", "min_fine_php", "total_sections",
    "enacting_president", "target_audience", "source_url",
)

# Text columns searched by keyword (the same 13 fields the original /search endpoint used).
SEARCH_COLUMNS = (
    "ra_number", "official_title", "plain_title", "category", "status", "enacting_president",
    "target_audience", "tldr_summary", "full_breakdown", "why_it_matters", "example_scenario",
    "penalties",
)

# Each law row comes back with its comments as a JSON list, so one query serves the page.
LAW_SELECT = """
    SELECT l.*,
           COALESCE((
               SELECT json_agg(json_build_object(
                          'id', c.id, 'user_name', c.user_name,
                          'comment', c.comment, 'created_at', c.created_at)
                      ORDER BY c.created_at, c.id)
               FROM comments c WHERE c.law_id = l.id
           ), '[]'::json) AS user_notes
    FROM laws l
"""

PREVIEW_IDS = f"SELECT id FROM laws ORDER BY id LIMIT {GUEST_PREVIEW_SIZE}"


# ----------------------------------------------------------------------
# Connection
# ----------------------------------------------------------------------
class LazyConnection:
    """Opens the real connection on first use, so requests rejected by auth or
    validation (401/403/422) never open a database connection."""

    def __init__(self):
        self._conn = None

    def _open(self):
        if self._conn is None:
            url = os.environ.get("DATABASE_URL")
            if not url:
                log.error("DATABASE_URL is not set")
                raise HTTPException(status_code=503, detail="Database temporarily unavailable.")
            try:
                self._conn = psycopg2.connect(url, cursor_factory=RealDictCursor, connect_timeout=10)
            except psycopg2.OperationalError:
                log.exception("Could not connect to the database")
                raise HTTPException(status_code=503, detail="Database temporarily unavailable.")
        return self._conn

    def cursor(self):
        return self._open().cursor()

    def commit(self):
        self._open().commit()

    def rollback(self):
        if self._conn is not None:
            self._conn.rollback()

    def close(self):
        if self._conn is not None:
            self._conn.close()


def get_db():
    """FastAPI dependency: one short connection per request through Neon's pooler.
    Any error rolls the transaction back; the connection always closes."""
    conn = LazyConnection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ping(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        return cur.fetchone()["ok"] == 1


# ----------------------------------------------------------------------
# Laws: read
# ----------------------------------------------------------------------
def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_laws(conn, *, guest: bool, category=None, search=None):
    """Shared by GET /laws and GET /laws/search, so both return the same results.

    Guests are limited to the preview set inside the query itself.
    Returns (laws, total) where total is the number of laws in the whole table.
    """
    where, params = [], []
    if guest:
        where.append(f"l.id IN ({PREVIEW_IDS})")
    if category:
        where.append("l.category = %s")
        params.append(category)
    if search:
        pattern = f"%{_escape_like(search)}%"
        ors = [f"l.{col} ILIKE %s" for col in SEARCH_COLUMNS] + ["l.year::text ILIKE %s"]
        where.append("(" + " OR ".join(ors) + ")")
        params.extend([pattern] * len(ors))

    sql = LAW_SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY l.id"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        laws = cur.fetchall()
        cur.execute("SELECT COUNT(*) AS n FROM laws")
        total = cur.fetchone()["n"]
    return laws, total


def get_law(conn, law_id: int):
    with conn.cursor() as cur:
        cur.execute(LAW_SELECT + " WHERE l.id = %s", (law_id,))
        return cur.fetchone()


def is_in_preview(conn, law_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(f"SELECT %s IN ({PREVIEW_IDS}) AS inside", (law_id,))
        return cur.fetchone()["inside"]


def stats(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT category, COUNT(*) AS n FROM laws GROUP BY category")
        by_category = {row["category"]: row["n"] for row in cur.fetchall()}
    return {"total": sum(by_category.values()), "categories": by_category}


# ----------------------------------------------------------------------
# Laws: write (each commits before returning)
# ----------------------------------------------------------------------
def create_law(conn, data: dict):
    cols = [c for c in LAW_COLUMNS if c in data]
    sql = (
        f"INSERT INTO laws ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        "RETURNING id"
    )
    with conn.cursor() as cur:
        cur.execute(sql, [data[c] for c in cols])
        new_id = cur.fetchone()["id"]
    conn.commit()
    return get_law(conn, new_id)


def update_law(conn, law_id: int, changes: dict):
    cols = [c for c in LAW_COLUMNS if c in changes]  # whitelist: never trust request keys
    sets = ", ".join(f"{c} = %s" for c in cols) + ", updated_at = now()"
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE laws SET {sets} WHERE id = %s RETURNING id",
            [changes[c] for c in cols] + [law_id],
        )
        row = cur.fetchone()
    conn.commit()
    return get_law(conn, law_id) if row else None


def delete_law(conn, law_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM laws WHERE id = %s RETURNING id", (law_id,))
        row = cur.fetchone()
    conn.commit()
    return row is not None


# ----------------------------------------------------------------------
# Comments
# ----------------------------------------------------------------------
def add_comment(conn, law_id: int, user_id: int, user_name: str, comment: str):
    """Raises psycopg2.errors.ForeignKeyViolation if the law does not exist (mapped to 404)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO comments (law_id, user_id, user_name, comment) VALUES (%s, %s, %s, %s)",
            (law_id, user_id, user_name, comment),
        )
    conn.commit()
    return get_law(conn, law_id)["user_notes"]


# ----------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------
def get_user_by_username(conn, username: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = %s",
            (username,),
        )
        return cur.fetchone()

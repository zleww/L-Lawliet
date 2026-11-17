"""Database access for L-Lawliet: the connection dependency and every SQL query.

All values are passed as %s parameters, never formatted into the SQL string.
Column names in UPDATE come only from LAW_COLUMNS / PROFILE_COLUMNS, never from the request.
Every write first tells PostgreSQL who is acting (act_as), so the Row-Level Security
policies in scripts/migrate_003_security_rules.sql can check it.
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
                          'id', c.id, 'user_id', c.user_id, 'user_name', c.user_name,
                          'comment', c.comment, 'created_at', c.created_at,
                          'edited_at', c.updated_at)
                      ORDER BY c.created_at, c.id)
               FROM comments c WHERE c.law_id = l.id
           ), '[]'::json) AS user_notes
    FROM laws l
"""

PREVIEW_IDS = f"SELECT id FROM laws ORDER BY id LIMIT {GUEST_PREVIEW_SIZE}"

PROFILE_COLUMNS = ("display_name", "bio", "theme", "accent")

# What the API may send back about an account (never password_hash or google_sub).
USER_PUBLIC = """
    SELECT id, username, role, email, display_name, bio, theme, accent, token_version,
           created_at, password_hash IS NOT NULL AS has_password,
           google_sub IS NOT NULL AS google_linked
    FROM users
"""

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


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


def act_as(cur, user):
    """Tell PostgreSQL who is making this change, for the RLS policies. The values are
    local to the current transaction (is_local = true), so they cannot leak to another
    request through Neon's connection pooler. Call it in the same transaction as the write."""
    cur.execute(
        "SELECT set_config('app.user_id', %s, true), set_config('app.role', %s, true)",
        (str(user["id"]) if user else "", user["role"] if user else "guest"),
    )


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
def create_law(conn, data: dict, actor: dict):
    cols = [c for c in LAW_COLUMNS if c in data]
    sql = (
        f"INSERT INTO laws ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
        "RETURNING id"
    )
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(sql, [data[c] for c in cols])
        new_id = cur.fetchone()["id"]
    conn.commit()
    return get_law(conn, new_id)


def update_law(conn, law_id: int, changes: dict, actor: dict):
    cols = [c for c in LAW_COLUMNS if c in changes]  # whitelist: never trust request keys
    sets = ", ".join(f"{c} = %s" for c in cols) + ", updated_at = now()"
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            f"UPDATE laws SET {sets} WHERE id = %s RETURNING id",
            [changes[c] for c in cols] + [law_id],
        )
        row = cur.fetchone()
    conn.commit()
    return get_law(conn, law_id) if row else None


def delete_law(conn, law_id: int, actor: dict) -> bool:
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("DELETE FROM laws WHERE id = %s RETURNING id", (law_id,))
        row = cur.fetchone()
    conn.commit()
    return row is not None


# ----------------------------------------------------------------------
# Comments
# ----------------------------------------------------------------------
def add_comment(conn, law_id: int, actor: dict, user_name: str, comment: str):
    """Raises psycopg2.errors.ForeignKeyViolation if the law does not exist (mapped to 404)."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO comments (law_id, user_id, user_name, comment) VALUES (%s, %s, %s, %s)",
            (law_id, actor["id"], user_name, comment),
        )
    conn.commit()
    return get_law(conn, law_id)["user_notes"]


def get_comment(conn, comment_id: int):
    with conn.cursor() as cur:
        cur.execute("SELECT id, law_id, user_id FROM comments WHERE id = %s", (comment_id,))
        return cur.fetchone()


def update_comment(conn, comment_id: int, actor: dict, text: str):
    """Only the author's own comment changes. The route checks ownership first, and the
    comments_update_own policy makes PostgreSQL refuse anyone else's row as well."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "UPDATE comments SET comment = %s, updated_at = now() WHERE id = %s RETURNING law_id",
            (text, comment_id),
        )
        row = cur.fetchone()
    conn.commit()
    return get_law(conn, row["law_id"])["user_notes"] if row else None


# ----------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------
def get_user_by_username(conn, username: str):
    """For login only: includes password_hash and the lockout fields. Case-insensitive."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, password_hash, role, token_version, failed_logins, locked_until, "
            "locked_until > now() AS is_locked, "
            "CEIL(EXTRACT(EPOCH FROM (locked_until - now())) / 60)::int AS minutes_left "
            "FROM users WHERE lower(username) = lower(%s)",
            (username,),
        )
        return cur.fetchone()


def get_user_by_id(conn, user_id: int):
    with conn.cursor() as cur:
        cur.execute(USER_PUBLIC + " WHERE id = %s", (user_id,))
        return cur.fetchone()


def get_user_by_google_sub(conn, google_sub: str):
    with conn.cursor() as cur:
        cur.execute(USER_PUBLIC + " WHERE google_sub = %s", (google_sub,))
        return cur.fetchone()


def get_password_hash(conn, user_id: int):
    with conn.cursor() as cur:
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return row["password_hash"] if row else None


def username_taken(conn, username: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE lower(username) = lower(%s)", (username,))
        return cur.fetchone() is not None


def create_user(conn, *, username: str, password_hash=None, display_name=None,
                email=None, google_sub=None):
    """New accounts are always role 'user' (the users_signup policy also enforces it).
    Raises psycopg2.errors.UniqueViolation if the username or Google account is taken."""
    with conn.cursor() as cur:
        act_as(cur, None)
        cur.execute(
            "INSERT INTO users (username, password_hash, role, display_name, email, google_sub) "
            "VALUES (%s, %s, 'user', %s, %s, %s) RETURNING id",
            (username, password_hash, display_name, email, google_sub),
        )
        new_id = cur.fetchone()["id"]
    conn.commit()
    return get_user_by_id(conn, new_id)


def record_failed_login(conn, account: dict):
    """Count a wrong password. The 5th in a row locks the account for 15 minutes.
    Runs as the account being logged into, so the users_update_self policy allows it."""
    with conn.cursor() as cur:
        act_as(cur, account)
        cur.execute(
            "UPDATE users SET "
            "  failed_logins = CASE WHEN failed_logins + 1 >= %s THEN 0 ELSE failed_logins + 1 END, "
            "  locked_until  = CASE WHEN failed_logins + 1 >= %s "
            "                       THEN now() + make_interval(mins => %s) ELSE locked_until END "
            "WHERE id = %s",
            (MAX_FAILED_LOGINS, MAX_FAILED_LOGINS, LOCKOUT_MINUTES, account["id"]),
        )
    conn.commit()


def clear_failed_logins(conn, account: dict):
    with conn.cursor() as cur:
        act_as(cur, account)
        cur.execute(
            "UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = %s", (account["id"],)
        )
    conn.commit()


def update_profile(conn, actor: dict, changes: dict):
    cols = [c for c in PROFILE_COLUMNS if c in changes]  # whitelist: never trust request keys
    values = [(changes[c] or None) if c == "bio" else changes[c] for c in cols]  # "" clears the bio
    sets = ", ".join(f"{c} = %s" for c in cols) + ", updated_at = now()"
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(f"UPDATE users SET {sets} WHERE id = %s", values + [actor["id"]])
    conn.commit()
    return get_user_by_id(conn, actor["id"])


def set_password(conn, actor: dict, password_hash: str):
    """New password and a new token_version, so every other login is signed out."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "UPDATE users SET password_hash = %s, token_version = token_version + 1, "
            "updated_at = now() WHERE id = %s",
            (password_hash, actor["id"]),
        )
    conn.commit()
    return get_user_by_id(conn, actor["id"])


def bump_token_version(conn, actor: dict):
    """Log out of all devices: every token issued before now stops working."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "UPDATE users SET token_version = token_version + 1 WHERE id = %s", (actor["id"],)
        )
    conn.commit()


def count_admins(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")
        return cur.fetchone()["n"]


def delete_user(conn, actor: dict):
    """Deletes the account in one transaction. Its comments stay on the laws, shown as
    'Deleted user' (user_id becomes NULL through ON DELETE SET NULL)."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("UPDATE comments SET user_name = 'Deleted user' WHERE user_id = %s", (actor["id"],))
        cur.execute("DELETE FROM users WHERE id = %s RETURNING id", (actor["id"],))
        row = cur.fetchone()
    conn.commit()
    return row is not None

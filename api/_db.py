"""Database access for L-Lawliet: the connection dependency and every SQL query.

All values are passed as %s parameters, never formatted into the SQL string.
Column names in UPDATE come only from LAW_COLUMNS / PROFILE_COLUMNS, never from the request.
Every write first tells PostgreSQL who is acting (act_as), so the Row-Level Security
policies in scripts/migrate_003_security_rules.sql can check it.
"""
import hashlib
import logging
import os
import re
from typing import Optional

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

# Each law row comes back with its notes as a JSON list (most helpful first) and its
# average rating, so one query serves the page.
LAW_SELECT = """
    SELECT l.*,
           COALESCE((
               SELECT json_agg(json_build_object(
                          'id', n.id, 'user_id', n.user_id, 'user_name', n.user_name,
                          'comment', n.comment, 'created_at', n.created_at,
                          'edited_at', n.updated_at, 'helpful_count', n.helpful)
                      ORDER BY n.helpful DESC, n.created_at, n.id)
               FROM (SELECT c.*, (SELECT COUNT(*) FROM comment_votes v WHERE v.comment_id = c.id) AS helpful
                     FROM comments c WHERE c.law_id = l.id) n
           ), '[]'::json) AS user_notes,
           (SELECT ROUND(AVG(r.rating), 1)::float FROM law_ratings r WHERE r.law_id = l.id) AS rating_avg,
           (SELECT COUNT(*) FROM law_ratings r WHERE r.law_id = l.id) AS rating_count
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


def get_law(conn, law_id: int, viewer=None):
    """One law with its notes. With a logged-in viewer it also says whether they saved it,
    their rating, and which notes they marked helpful."""
    with conn.cursor() as cur:
        cur.execute(LAW_SELECT + " WHERE l.id = %s", (law_id,))
        law = cur.fetchone()
        if law is None or viewer is None:
            return law
        act_as(cur, viewer)  # saved_laws is private: RLS needs to know who is reading
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM saved_laws WHERE user_id = %s AND law_id = %s) AS saved, "
            "(SELECT rating FROM law_ratings WHERE user_id = %s AND law_id = %s) AS my_rating",
            (viewer["id"], law_id, viewer["id"], law_id),
        )
        mine = cur.fetchone()
        cur.execute(
            "SELECT v.comment_id FROM comment_votes v JOIN comments c ON c.id = v.comment_id "
            "WHERE v.user_id = %s AND c.law_id = %s", (viewer["id"], law_id),
        )
        voted = {row["comment_id"] for row in cur.fetchall()}
    law["saved"], law["my_rating"] = mine["saved"], mine["my_rating"]
    for note in law["user_notes"]:
        note["voted_by_me"] = note["id"] in voted
    return law


def is_in_preview(conn, law_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(f"SELECT %s IN ({PREVIEW_IDS}) AS inside", (law_id,))
        return cur.fetchone()["inside"]


def stats(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT category, COUNT(*) AS n FROM laws GROUP BY category")
        by_category = {row["category"]: row["n"] for row in cur.fetchall()}
        cur.execute("SELECT COUNT(*) AS n FROM law_index")
        listed = cur.fetchone()["n"]
    return {"total": sum(by_category.values()), "categories": by_category, "listed": listed}


# ----------------------------------------------------------------------
# Full list of statutes (law_index): public, read only
# ----------------------------------------------------------------------
# "RA 10175", "R.A. No. 10175", "Republic Act 10175", "PD 1606", "BP 22", "10175"
_NUMBER_QUERY = re.compile(
    r"^\s*(?:(?P<type>r\.?\s*a|republic\s+act|c\.?\s*a|commonwealth\s+act|p\.?\s*d|presidential\s+decree"
    r"|b\.?\s*p|batas\s+pambansa|act)\.?\s*(?:no\.?|blg\.?|number)?\s*)?(?P<num>\d+[a-z]?)\s*$",
    re.I,
)


def _law_type_of(word: Optional[str]) -> Optional[str]:
    if not word:
        return None
    w = re.sub(r"[\s.]", "", word.lower())
    return {"ra": "ra", "republicact": "ra", "ca": "ca", "commonwealthact": "ca", "pd": "pd",
            "presidentialdecree": "pd", "bp": "bp", "bataspambansa": "bp", "act": "act"}[w]


INDEX_SELECT = (
    "SELECT i.id, i.law_type, i.number, i.label, i.enacted_on, i.year, i.official_title, "
    "i.source_url, i.law_id FROM law_index i"
)
INDEX_ORDER = "i.year DESC, NULLIF(regexp_replace(i.number, '\\D', '', 'g'), '')::int DESC"


def list_law_index(conn, *, q=None, law_type=None, year=None, page=1, per_page=25):
    """One page of the full statute list, newest first, or best match first when searching.
    A query that is just a law number ("RA 10175", "10175") matches that number exactly."""
    where, params, order, order_params = [], [], INDEX_ORDER, []
    if law_type:
        where.append("i.law_type = %s")
        params.append(law_type)
    if year:
        where.append("i.year = %s")
        params.append(year)
    if q:
        m = _NUMBER_QUERY.match(q)
        if m:
            where.append("lower(i.number) = lower(%s)")
            params.append(m["num"])
            typed = _law_type_of(m["type"])
            if typed:
                where.append("i.law_type = %s")
                params.append(typed)
        else:
            where.append("i.search @@ websearch_to_tsquery('english', %s)")
            params.append(q)
            order = "ts_rank(i.search, websearch_to_tsquery('english', %s)) DESC, " + INDEX_ORDER
            order_params = [q]
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM law_index i" + clause, params)
        total = cur.fetchone()["n"]
        cur.execute(
            INDEX_SELECT + clause + f" ORDER BY {order} LIMIT %s OFFSET %s",
            params + order_params + [per_page, (page - 1) * per_page],
        )
        items = cur.fetchall()
    for item in items:
        if item["enacted_on"] is not None:
            item["enacted_on"] = item["enacted_on"].isoformat()
    return items, total


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
    return get_law(conn, law_id, actor)["user_notes"]


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
    return get_law(conn, row["law_id"], actor)["user_notes"] if row else None


def delete_comment(conn, comment_id: int, actor: dict) -> bool:
    """The route checks author-or-admin first; the comments_delete_own policy
    (migration 004) makes PostgreSQL refuse anyone else's row as well."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("DELETE FROM comments WHERE id = %s RETURNING id", (comment_id,))
        row = cur.fetchone()
    conn.commit()
    return row is not None


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


def bump_token_version(conn, actor: dict, target_id=None) -> bool:
    """Log out of all devices: every token issued before now stops working.
    target_id = another account (admins only, through the users_admin_update policy)."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "UPDATE users SET token_version = token_version + 1 WHERE id = %s RETURNING id",
            (target_id or actor["id"],),
        )
        row = cur.fetchone()
    conn.commit()
    return row is not None


def count_admins(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")
        return cur.fetchone()["n"]


def delete_user(conn, actor: dict, target_id=None):
    """Deletes the account in one transaction. Its comments stay on the laws, shown as
    'Deleted user' (user_id becomes NULL through ON DELETE SET NULL). Saves, ratings and
    votes go with it. target_id = another account (admins only; never an admin account)."""
    target = target_id or actor["id"]
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("UPDATE comments SET user_name = 'Deleted user' WHERE user_id = %s", (target,))
        cur.execute("DELETE FROM users WHERE id = %s RETURNING id", (target,))
        row = cur.fetchone()
    conn.commit()
    return row is not None


# ----------------------------------------------------------------------
# Email links: verify a recovery email, reset a forgotten password (migration 008)
# Only a SHA-256 hash of each link's token is stored, so a database leak cannot be
# turned into working links. Every link works once and expires.
# ----------------------------------------------------------------------
RESET_MINUTES = 30
VERIFY_HOURS = 24
MAX_LINKS_PER_HOUR = 3  # per account and purpose, so the API cannot be used to spam an inbox


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def get_user_for_reset(conn, login: str):
    """Find an account by username, or by verified email when the input contains '@'."""
    column = "email" if "@" in login else "username"
    with conn.cursor() as cur:
        cur.execute(USER_PUBLIC + f" WHERE lower({column}) = lower(%s)", (login,))
        return cur.fetchone()


def email_taken(conn, email: str, except_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE lower(email) = lower(%s) AND id <> %s", (email, except_id))
        return cur.fetchone() is not None


def recent_link_count(conn, user_id: int, purpose: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM account_tokens "
            "WHERE user_id = %s AND purpose = %s AND created_at > now() - interval '1 hour'",
            (user_id, purpose),
        )
        return cur.fetchone()["n"]


def create_account_token(conn, account: dict, purpose: str, email: str, token_hash: str, minutes: int):
    """Runs as the account itself, so the account_tokens_insert_own policy allows it."""
    with conn.cursor() as cur:
        act_as(cur, account)
        cur.execute(
            "INSERT INTO account_tokens (user_id, purpose, email, token_hash, expires_at) "
            "VALUES (%s, %s, %s, %s, now() + make_interval(mins => %s))",
            (account["id"], purpose, email, token_hash, minutes),
        )
    conn.commit()


def find_account_token(conn, token_hash: str, purpose: str):
    """The token row if it exists, is unused and has not expired; otherwise None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, user_id, email FROM account_tokens "
            "WHERE token_hash = %s AND purpose = %s AND used_at IS NULL AND expires_at > now()",
            (token_hash, purpose),
        )
        return cur.fetchone()


def _use_token(cur, token_id: int, user_id: int, purpose: str) -> bool:
    """Marks this link used (only once, even if two requests race) and retires the
    account's other unused links of the same kind."""
    cur.execute(
        "UPDATE account_tokens SET used_at = now() WHERE id = %s AND used_at IS NULL RETURNING id",
        (token_id,),
    )
    if cur.fetchone() is None:
        return False
    cur.execute(
        "UPDATE account_tokens SET used_at = now() "
        "WHERE user_id = %s AND purpose = %s AND used_at IS NULL",
        (user_id, purpose),
    )
    return True


def reset_password_with_token(conn, token: dict, password_hash: str):
    """New password, signs out every device (token_version + 1) and clears any lockout.
    Returns the account, or None if the link was used in the meantime."""
    account = get_user_by_id(conn, token["user_id"])
    if account is None:
        return None
    with conn.cursor() as cur:
        act_as(cur, account)
        if not _use_token(cur, token["id"], account["id"], "reset_password"):
            conn.rollback()
            return None
        cur.execute(
            "UPDATE users SET password_hash = %s, token_version = token_version + 1, "
            "failed_logins = 0, locked_until = NULL, updated_at = now() WHERE id = %s",
            (password_hash, account["id"]),
        )
    conn.commit()
    return get_user_by_id(conn, account["id"])


def verify_email_with_token(conn, token: dict):
    """Saves the confirmed email on the account. Returns the account, or None if the link
    was used in the meantime. UniqueViolation if another account confirmed it first."""
    account = get_user_by_id(conn, token["user_id"])
    if account is None:
        return None
    with conn.cursor() as cur:
        act_as(cur, account)
        if not _use_token(cur, token["id"], account["id"], "verify_email"):
            conn.rollback()
            return None
        cur.execute(
            "UPDATE users SET email = %s, updated_at = now() WHERE id = %s",
            (token["email"], account["id"]),
        )
    conn.commit()
    return get_user_by_id(conn, account["id"])



# ----------------------------------------------------------------------
# Saved laws (private to each user)
# ----------------------------------------------------------------------
def list_saved(conn, actor: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "SELECT l.id, l.ra_number, l.plain_title, l.category, l.year, s.saved_at "
            "FROM saved_laws s JOIN laws l ON l.id = s.law_id "
            "WHERE s.user_id = %s ORDER BY s.saved_at DESC",
            (actor["id"],),
        )
        return cur.fetchall()


def save_law(conn, actor: dict, law_id: int):
    """UniqueViolation if already saved (409); ForeignKeyViolation if the law is missing (404)."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO saved_laws (user_id, law_id) VALUES (%s, %s) RETURNING saved_at",
            (actor["id"], law_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def unsave_law(conn, actor: dict, law_id: int) -> bool:
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "DELETE FROM saved_laws WHERE user_id = %s AND law_id = %s RETURNING law_id",
            (actor["id"], law_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row is not None


# ----------------------------------------------------------------------
# Ratings (one per user per law)
# ----------------------------------------------------------------------
def rating_summary(conn, law_id: int, viewer=None):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ROUND(AVG(rating), 1)::float AS rating_avg, COUNT(*) AS rating_count "
            "FROM law_ratings WHERE law_id = %s", (law_id,),
        )
        out = cur.fetchone()
        if viewer:
            cur.execute(
                "SELECT rating FROM law_ratings WHERE user_id = %s AND law_id = %s",
                (viewer["id"], law_id),
            )
            row = cur.fetchone()
            out["my_rating"] = row["rating"] if row else None
    return out


def set_rating(conn, actor: dict, law_id: int, rating: int):
    """Rating again changes the rating instead of adding a second one."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO law_ratings (user_id, law_id, rating) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id, law_id) DO UPDATE SET rating = EXCLUDED.rating, updated_at = now()",
            (actor["id"], law_id, rating),
        )
    conn.commit()
    return rating_summary(conn, law_id, actor)


def delete_rating(conn, actor: dict, law_id: int) -> bool:
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "DELETE FROM law_ratings WHERE user_id = %s AND law_id = %s RETURNING law_id",
            (actor["id"], law_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row is not None


# ----------------------------------------------------------------------
# Helpful votes on notes
# ----------------------------------------------------------------------
def helpful_count(conn, comment_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM comment_votes WHERE comment_id = %s", (comment_id,))
        return cur.fetchone()["n"]


def add_vote(conn, actor: dict, comment_id: int):
    """UniqueViolation if this user already voted on the note (409)."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO comment_votes (user_id, comment_id) VALUES (%s, %s)", (actor["id"], comment_id)
        )
    conn.commit()
    return helpful_count(conn, comment_id)


def remove_vote(conn, actor: dict, comment_id: int) -> bool:
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "DELETE FROM comment_votes WHERE user_id = %s AND comment_id = %s RETURNING comment_id",
            (actor["id"], comment_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row is not None


# ----------------------------------------------------------------------
# Reports on notes
# ----------------------------------------------------------------------
def add_report(conn, actor: dict, comment_id: int, reason: str, details):
    """UniqueViolation if this user already reported the note (409)."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO comment_reports (comment_id, reporter_id, reason, details) "
            "VALUES (%s, %s, %s, %s) RETURNING id, status, created_at",
            (comment_id, actor["id"], reason, details or None),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def list_reports(conn, admin: dict, status: str):
    """Admin queue: each report with the note, its law, its author and how many reports it has."""
    with conn.cursor() as cur:
        act_as(cur, admin)
        cur.execute(
            "SELECT r.id, r.reason, r.details, r.status, r.created_at, r.resolved_at, "
            "       c.id AS comment_id, c.comment, c.user_name AS author_name, c.user_id AS author_id, "
            "       l.id AS law_id, l.ra_number, rep.username AS reporter, "
            "       (SELECT COUNT(*) FROM comment_reports x WHERE x.comment_id = c.id AND x.status = 'open') "
            "         AS open_reports_on_note "
            "FROM comment_reports r "
            "JOIN comments c ON c.id = r.comment_id JOIN laws l ON l.id = c.law_id "
            "LEFT JOIN users rep ON rep.id = r.reporter_id "
            "WHERE r.status = %s ORDER BY r.created_at",
            (status,),
        )
        return cur.fetchall()


def resolve_report(conn, admin: dict, report_id: int, status: str):
    with conn.cursor() as cur:
        act_as(cur, admin)
        cur.execute(
            "UPDATE comment_reports SET status = %s, resolved_by = %s, resolved_at = now() "
            "WHERE id = %s RETURNING id, status, resolved_at",
            (status, admin["id"], report_id),
        )
        row = cur.fetchone()
    conn.commit()
    return row


# ----------------------------------------------------------------------
# Law suggestions
# ----------------------------------------------------------------------
SUGGESTION_COLUMNS = (
    "s.id, s.ra_number, s.title, s.reason, s.source_url, s.status, s.admin_note, "
    "s.created_at, s.reviewed_at, s.law_id"
)


def law_id_by_ra(conn, ra_number: str):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM laws WHERE upper(ra_number) = upper(%s)", (ra_number,))
        row = cur.fetchone()
        return row["id"] if row else None


def create_suggestion(conn, actor: dict, data: dict):
    """UniqueViolation if this user already has a pending suggestion for the RA number (409)."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO law_suggestions (user_id, ra_number, title, reason, source_url) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (actor["id"], data["ra_number"], data["title"], data["reason"], data.get("source_url")),
        )
        new_id = cur.fetchone()["id"]
        cur.execute(f"SELECT {SUGGESTION_COLUMNS} FROM law_suggestions s WHERE s.id = %s", (new_id,))
        row = cur.fetchone()
    conn.commit()
    return row


def list_my_suggestions(conn, actor: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            f"SELECT {SUGGESTION_COLUMNS} FROM law_suggestions s WHERE s.user_id = %s "
            "ORDER BY s.created_at DESC",
            (actor["id"],),
        )
        return cur.fetchall()


def list_suggestions(conn, admin: dict, status: str):
    with conn.cursor() as cur:
        act_as(cur, admin)
        cur.execute(
            f"SELECT {SUGGESTION_COLUMNS}, u.username AS suggested_by "
            "FROM law_suggestions s LEFT JOIN users u ON u.id = s.user_id "
            "WHERE s.status = %s ORDER BY s.created_at",
            (status,),
        )
        return cur.fetchall()


def get_suggestion_status(conn, admin: dict, suggestion_id: int):
    with conn.cursor() as cur:
        act_as(cur, admin)
        cur.execute("SELECT status FROM law_suggestions WHERE id = %s", (suggestion_id,))
        row = cur.fetchone()
    return row["status"] if row else None


def review_suggestion(conn, admin: dict, suggestion_id: int, status: str, admin_note, law_id):
    """Only a pending suggestion can be reviewed; returns None otherwise."""
    with conn.cursor() as cur:
        act_as(cur, admin)
        cur.execute(
            "UPDATE law_suggestions SET status = %s, admin_note = %s, law_id = %s, "
            "reviewed_by = %s, reviewed_at = now() "
            "WHERE id = %s AND status = 'pending' RETURNING id",
            (status, admin_note or None, law_id, admin["id"], suggestion_id),
        )
        row = cur.fetchone()
        if row:
            cur.execute(f"SELECT {SUGGESTION_COLUMNS} FROM law_suggestions s WHERE s.id = %s", (suggestion_id,))
            row = cur.fetchone()
    conn.commit()
    return row


# ----------------------------------------------------------------------
# Public profiles and the admin user list
# ----------------------------------------------------------------------
def get_profile(conn, user_id: int):
    """What another logged-in user may see: no email, no settings, no saved laws."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, display_name, bio, role, created_at FROM users WHERE id = %s",
            (user_id,),
        )
        profile = cur.fetchone()
        if profile is None:
            return None
        cur.execute(
            "SELECT c.id, c.comment, c.created_at, c.updated_at AS edited_at, "
            "       l.id AS law_id, l.ra_number, l.plain_title, "
            "       (SELECT COUNT(*) FROM comment_votes v WHERE v.comment_id = c.id) AS helpful_count "
            "FROM comments c JOIN laws l ON l.id = c.law_id "
            "WHERE c.user_id = %s ORDER BY c.created_at DESC",
            (user_id,),
        )
        profile["notes"] = cur.fetchall()
    profile["note_count"] = len(profile["notes"])
    profile["helpful_received"] = sum(n["helpful_count"] for n in profile["notes"])
    return profile


def list_users(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.username, u.display_name, u.role, u.created_at, "
            "       u.google_sub IS NOT NULL AS google_linked, u.failed_logins, "
            "       COALESCE(u.locked_until > now(), false) AS is_locked, "
            "       (SELECT COUNT(*) FROM comments c WHERE c.user_id = u.id) AS note_count "
            "FROM users u ORDER BY u.id"
        )
        return cur.fetchall()


def get_user_role(conn, user_id: int):
    with conn.cursor() as cur:
        cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return row["role"] if row else None


def admin_unlock(conn, admin: dict, target_id: int) -> bool:
    with conn.cursor() as cur:
        act_as(cur, admin)
        cur.execute(
            "UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = %s RETURNING id",
            (target_id,),
        )
        row = cur.fetchone()
    conn.commit()
    return row is not None


# ----------------------------------------------------------------------
# Study data (JurisCard). Every query runs after act_as, because the RLS policies
# in scripts/migrate_006_study.sql only show a user their own rows.
# ----------------------------------------------------------------------
FLASHCARD_COLUMNS = ("category", "question", "answer", "source", "status")
PREF_COLUMNS = ("quiz_length", "daily_goal", "hide_mastered")
DEFAULT_PREFS = {"quiz_length": 10, "daily_goal": 10, "hide_mastered": False}

# Midnight today in the Philippines, so "today" matches the student's clock.
TODAY_START = "(date_trunc('day', now() AT TIME ZONE 'Asia/Manila') AT TIME ZONE 'Asia/Manila')"

FLASHCARD_SELECT = (
    "SELECT id, category, question, answer, source, status, created_at, updated_at FROM flashcards"
)


def list_flashcards(conn, actor: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(FLASHCARD_SELECT + " WHERE user_id = %s ORDER BY created_at DESC, id DESC",
                    (actor["id"],))
        return cur.fetchall()


def create_flashcard(conn, actor: dict, data: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO flashcards (user_id, category, question, answer, source) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (actor["id"], data["category"], data["question"], data["answer"], data.get("source") or None),
        )
        new_id = cur.fetchone()["id"]
        cur.execute(FLASHCARD_SELECT + " WHERE id = %s", (new_id,))
        row = cur.fetchone()
    conn.commit()
    return row


def update_flashcard(conn, actor: dict, card_id: int, changes: dict):
    """Returns None when the card does not exist or belongs to someone else (RLS hides it)."""
    cols = [c for c in FLASHCARD_COLUMNS if c in changes]  # whitelist: never trust request keys
    values = [(changes[c] or None) if c == "source" else changes[c] for c in cols]
    sets = ", ".join(f"{c} = %s" for c in cols) + ", updated_at = now()"
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(f"UPDATE flashcards SET {sets} WHERE id = %s AND user_id = %s RETURNING id",
                    values + [card_id, actor["id"]])
        found = cur.fetchone()
        row = None
        if found:
            cur.execute(FLASHCARD_SELECT + " WHERE id = %s", (card_id,))
            row = cur.fetchone()
    conn.commit()
    return row


def delete_flashcard(conn, actor: dict, card_id: int) -> bool:
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("DELETE FROM flashcards WHERE id = %s AND user_id = %s RETURNING id",
                    (card_id, actor["id"]))
        row = cur.fetchone()
    conn.commit()
    return row is not None


def list_progress(conn, actor: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("SELECT law_id, status, updated_at FROM law_progress WHERE user_id = %s ORDER BY law_id",
                    (actor["id"],))
        return cur.fetchall()


def set_progress(conn, actor: dict, law_id: int, status: str):
    """'review' or 'mastered' saves the mark; 'new' removes it. Raises ForeignKeyViolation
    (mapped to 404) if the law does not exist."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        if status == "new":
            cur.execute("DELETE FROM law_progress WHERE user_id = %s AND law_id = %s", (actor["id"], law_id))
        else:
            cur.execute(
                "INSERT INTO law_progress (user_id, law_id, status) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id, law_id) DO UPDATE SET status = EXCLUDED.status, updated_at = now()",
                (actor["id"], law_id, status),
            )
    conn.commit()
    return {"law_id": law_id, "status": status}


def reset_progress(conn, actor: dict) -> int:
    """Clears every law mark and sets the user's own cards back to 'new'."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("DELETE FROM law_progress WHERE user_id = %s", (actor["id"],))
        cleared = cur.rowcount
        cur.execute("UPDATE flashcards SET status = 'new', updated_at = now() "
                    "WHERE user_id = %s AND status <> 'new'", (actor["id"],))
        cleared += cur.rowcount
    conn.commit()
    return cleared


def add_quiz_attempt(conn, actor: dict, data: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO quiz_attempts (user_id, category, score, total) VALUES (%s, %s, %s, %s) "
            "RETURNING id, category, score, total, taken_at",
            (actor["id"], data.get("category"), data["score"], data["total"]),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def list_quiz_attempts(conn, actor: dict, limit: int = 20):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "SELECT id, category, score, total, taken_at FROM quiz_attempts WHERE user_id = %s "
            "ORDER BY taken_at DESC, id DESC LIMIT %s",
            (actor["id"], limit),
        )
        return cur.fetchall()


def get_prefs(conn, actor: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("SELECT quiz_length, daily_goal, hide_mastered FROM study_prefs WHERE user_id = %s",
                    (actor["id"],))
        row = cur.fetchone()
    return dict(row) if row else dict(DEFAULT_PREFS)


def update_prefs(conn, actor: dict, changes: dict):
    merged = {**get_prefs(conn, actor), **{c: changes[c] for c in PREF_COLUMNS if c in changes}}
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO study_prefs (user_id, quiz_length, daily_goal, hide_mastered) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET "
            "quiz_length = EXCLUDED.quiz_length, daily_goal = EXCLUDED.daily_goal, "
            "hide_mastered = EXCLUDED.hide_mastered, updated_at = now()",
            (actor["id"], merged["quiz_length"], merged["daily_goal"], merged["hide_mastered"]),
        )
    conn.commit()
    return merged


def study_summary(conn, actor: dict):
    """Everything the JurisCard dashboard and review pages show, in one round trip."""
    uid = actor["id"]
    with conn.cursor() as cur:
        act_as(cur, actor)
        # Per category: laws in the database, and how many of them / of my own cards I marked.
        cur.execute(
            """
            SELECT l.category,
                   COUNT(l.id)                                          AS laws,
                   COUNT(p.law_id) FILTER (WHERE p.status = 'mastered') AS laws_mastered,
                   COUNT(p.law_id) FILTER (WHERE p.status = 'review')   AS laws_review
            FROM laws l
            LEFT JOIN law_progress p ON p.law_id = l.id AND p.user_id = %s
            GROUP BY l.category ORDER BY l.category
            """,
            (uid,),
        )
        by_category = {r["category"]: {**r, "cards": 0, "cards_mastered": 0, "cards_review": 0}
                       for r in cur.fetchall()}
        cur.execute(
            "SELECT category, COUNT(*) AS cards, "
            "COUNT(*) FILTER (WHERE status = 'mastered') AS cards_mastered, "
            "COUNT(*) FILTER (WHERE status = 'review') AS cards_review "
            "FROM flashcards WHERE user_id = %s GROUP BY category",
            (uid,),
        )
        for r in cur.fetchall():
            row = by_category.setdefault(r["category"], {
                "category": r["category"], "laws": 0, "laws_mastered": 0, "laws_review": 0})
            row.update(cards=r["cards"], cards_mastered=r["cards_mastered"], cards_review=r["cards_review"])

        cur.execute(
            f"SELECT (SELECT COUNT(*) FROM law_progress WHERE user_id = %s AND updated_at >= {TODAY_START})"
            f" + (SELECT COUNT(*) FROM flashcards WHERE user_id = %s AND status <> 'new'"
            f"    AND updated_at >= {TODAY_START}) AS marked_today",
            (uid, uid),
        )
        marked_today = cur.fetchone()["marked_today"]

        cur.execute(
            "SELECT COUNT(*) AS attempts, "
            "ROUND(AVG(score * 100.0 / total))::int AS average_pct, "
            "MAX(ROUND(score * 100.0 / total))::int AS best_pct "
            "FROM quiz_attempts WHERE user_id = %s",
            (uid,),
        )
        quizzes = cur.fetchone()

        # Latest things the user did, newest first.
        cur.execute(
            """
            (SELECT 'progress' AS kind, p.law_id AS ref_id, p.updated_at AS at, p.status AS detail,
                    l.ra_number AS title, l.plain_title AS subtitle, l.category
             FROM law_progress p JOIN laws l ON l.id = p.law_id WHERE p.user_id = %s
             ORDER BY p.updated_at DESC LIMIT 8)
            UNION ALL
            (SELECT 'quiz', id, taken_at, score || ' / ' || total, NULL, NULL, category
             FROM quiz_attempts WHERE user_id = %s ORDER BY taken_at DESC LIMIT 8)
            UNION ALL
            (SELECT 'card', id, created_at, NULL, NULL, question, category
             FROM flashcards WHERE user_id = %s ORDER BY created_at DESC LIMIT 8)
            ORDER BY at DESC LIMIT 8
            """,
            (uid, uid, uid),
        )
        recent = cur.fetchall()
    return {
        "categories": list(by_category.values()),
        "marked_today": marked_today,
        "quizzes": quizzes,
        "recent": recent,
        "prefs": get_prefs(conn, actor),
    }


# ----------------------------------------------------------------------
# Admin overview (read only)
# ----------------------------------------------------------------------
def admin_overview(conn, actor: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            """
            SELECT (SELECT COUNT(*) FROM users)                                       AS users,
                   (SELECT COUNT(*) FROM users WHERE role = 'admin')                  AS admins,
                   (SELECT COUNT(*) FROM users
                     WHERE created_at >= now() - interval '7 days')                   AS new_this_week,
                   (SELECT COUNT(*) FROM laws)                                        AS laws,
                   (SELECT COUNT(*) FROM comments)                                    AS comments,
                   (SELECT COUNT(*) FROM flashcards)                                  AS flashcards,
                   (SELECT COUNT(*) FROM law_progress WHERE status = 'mastered')      AS laws_mastered,
                   (SELECT COUNT(*) FROM quiz_attempts)                               AS quiz_attempts,
                   (SELECT ROUND(AVG(score * 100.0 / total))::int FROM quiz_attempts) AS quiz_average_pct
            """
        )
        return cur.fetchone()


def admin_study_activity(conn, actor: dict):
    """Accounts with their study activity. No password hashes, emails or Google ids."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            """
            SELECT u.id, u.username, u.display_name, u.role, u.created_at,
                   (SELECT COUNT(*) FROM comments c WHERE c.user_id = u.id)          AS notes,
                   (SELECT COUNT(*) FROM flashcards f WHERE f.user_id = u.id)        AS flashcards,
                   (SELECT COUNT(*) FROM law_progress p
                     WHERE p.user_id = u.id AND p.status = 'mastered')               AS laws_mastered,
                   (SELECT COUNT(*) FROM quiz_attempts q WHERE q.user_id = u.id)     AS quizzes,
                   (SELECT ROUND(AVG(q.score * 100.0 / q.total))::int
                      FROM quiz_attempts q WHERE q.user_id = u.id)                   AS quiz_average_pct,
                   GREATEST(
                       (SELECT MAX(updated_at) FROM law_progress p WHERE p.user_id = u.id),
                       (SELECT MAX(taken_at)   FROM quiz_attempts q WHERE q.user_id = u.id),
                       (SELECT MAX(updated_at) FROM flashcards f WHERE f.user_id = u.id),
                       (SELECT MAX(created_at) FROM comments c WHERE c.user_id = u.id)
                   ) AS last_active
            FROM users u ORDER BY u.created_at DESC, u.id DESC
            """
        )
        return cur.fetchall()


# ----------------------------------------------------------------------
# Game data (JustGiveupATP / JurisCards Arena). Tables from scripts/migrate_007_arena.sql.
# Results are public (leaderboard); settings are private to each player.
# ----------------------------------------------------------------------
ARENA_PREF_COLUMNS = ("confirm_abandon", "reduce_motion", "hide_won")
DEFAULT_ARENA_PREFS = {"confirm_abandon": True, "reduce_motion": False, "hide_won": False}


def add_arena_result(conn, actor: dict, data: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO arena_results (user_id, case_id, tier, won, turns, jp_left) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, case_id, tier, won, turns, jp_left, played_at",
            (actor["id"], data["case_id"], data["tier"], data["won"], data["turns"], data["jp_left"]),
        )
        row = cur.fetchone()
    conn.commit()
    return row


def clear_arena_results(conn, actor: dict) -> int:
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("DELETE FROM arena_results WHERE user_id = %s", (actor["id"],))
        cleared = cur.rowcount
    conn.commit()
    return cleared


def get_arena_prefs(conn, actor: dict):
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute("SELECT confirm_abandon, reduce_motion, hide_won FROM arena_prefs WHERE user_id = %s",
                    (actor["id"],))
        row = cur.fetchone()
    return dict(row) if row else dict(DEFAULT_ARENA_PREFS)


def update_arena_prefs(conn, actor: dict, changes: dict):
    merged = {**get_arena_prefs(conn, actor), **{c: changes[c] for c in ARENA_PREF_COLUMNS if c in changes}}
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "INSERT INTO arena_prefs (user_id, confirm_abandon, reduce_motion, hide_won) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET "
            "confirm_abandon = EXCLUDED.confirm_abandon, reduce_motion = EXCLUDED.reduce_motion, "
            "hide_won = EXCLUDED.hide_won, updated_at = now()",
            (actor["id"], merged["confirm_abandon"], merged["reduce_motion"], merged["hide_won"]),
        )
    conn.commit()
    return merged


def arena_record(conn, actor: dict, history_limit: int = 20):
    """Cases won, totals and recent trials for one player."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            "SELECT case_id, COUNT(*) AS wins, MIN(turns) AS best_turns, MAX(jp_left) AS best_jp "
            "FROM arena_results WHERE user_id = %s AND won GROUP BY case_id ORDER BY case_id",
            (actor["id"],),
        )
        won = cur.fetchall()
        cur.execute(
            "SELECT COUNT(*) AS trials, COUNT(*) FILTER (WHERE won) AS wins FROM arena_results WHERE user_id = %s",
            (actor["id"],),
        )
        totals = cur.fetchone()
        cur.execute(
            "SELECT id, case_id, tier, won, turns, jp_left, played_at FROM arena_results "
            "WHERE user_id = %s ORDER BY played_at DESC, id DESC LIMIT %s",
            (actor["id"], history_limit),
        )
        history = cur.fetchall()
    return {
        "cases_won": won,
        "trials": totals["trials"],
        "wins": totals["wins"],
        "history": history,
        "prefs": get_arena_prefs(conn, actor),
    }


def arena_leaderboard(conn, limit: int = 20):
    """Players ranked by different cases won, then total wins. Display names only."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.id AS user_id, COALESCE(u.display_name, u.username) AS name, u.username,
                   COUNT(DISTINCT r.case_id) FILTER (WHERE r.won) AS cases_won,
                   COUNT(*) FILTER (WHERE r.won)                  AS wins,
                   COUNT(*)                                       AS trials,
                   MAX(r.played_at)                               AS last_played
            FROM arena_results r JOIN users u ON u.id = r.user_id
            GROUP BY u.id
            HAVING COUNT(*) FILTER (WHERE r.won) > 0
            ORDER BY cases_won DESC, wins DESC, last_played ASC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def admin_arena(conn, actor: dict):
    """Game activity across all players, for the JustGiveupATP admin page."""
    with conn.cursor() as cur:
        act_as(cur, actor)
        cur.execute(
            """
            SELECT COUNT(DISTINCT user_id)                                   AS players,
                   COUNT(*)                                                  AS trials,
                   COUNT(*) FILTER (WHERE won)                               AS wins,
                   COUNT(*) FILTER (WHERE played_at >= now() - interval '7 days') AS trials_this_week
            FROM arena_results
            """
        )
        overview = cur.fetchone()
        cur.execute(
            """
            SELECT case_id, MIN(tier) AS tier, COUNT(*) AS trials,
                   COUNT(*) FILTER (WHERE won) AS wins,
                   COUNT(DISTINCT user_id) AS players,
                   ROUND(AVG(turns) FILTER (WHERE won), 1) AS avg_turns_to_win
            FROM arena_results GROUP BY case_id ORDER BY MIN(tier), case_id
            """
        )
        cases = cur.fetchall()
        cur.execute(
            """
            SELECT u.id, u.username, u.display_name, u.role, u.created_at,
                   COUNT(r.id)                                     AS trials,
                   COUNT(r.id) FILTER (WHERE r.won)                AS wins,
                   COUNT(DISTINCT r.case_id) FILTER (WHERE r.won)  AS cases_won,
                   MAX(r.played_at)                                AS last_played
            FROM users u LEFT JOIN arena_results r ON r.user_id = u.id
            GROUP BY u.id ORDER BY last_played DESC NULLS LAST, u.created_at DESC
            """
        )
        players = cur.fetchall()
    return {"overview": overview, "cases": cases, "players": players}

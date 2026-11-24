"""Tests for forgot password, reset links and the recovery email (migration 008).

    python tests/reset_tests.py                      # against http://127.0.0.1:8000
    python tests/reset_tests.py https://<site>       # against a deployment

The server must be able to send email: SMTP_* set, or MAIL_DEV_LOG=1 for a local server.
Reads DATABASE_URL (lawliet_app) from .env: the emailed links cannot be read from an inbox
here, so the tests create their own link tokens in the database, acting as the test
account exactly like the API does, and check the RLS rules on account_tokens.
Creates throwaway accounts (prefix t_) and deletes them at the end; their links go with them.
"""
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass
import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2.extras import RealDictCursor

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
RUN = secrets.token_hex(3)
PASSWORD = f"Passw0rd{RUN}"
results = []
cleanup = {}  # username -> (token, password)


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=30) as res:
            raw = res.read()
            return res.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            return err.code, json.loads(raw)
        except ValueError:
            return err.code, raw.decode(errors="replace")


def check(test_id, name, ok, detail=""):
    ok = bool(ok)
    results.append((test_id, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {test_id}  {name}" + (f"  ({detail})" if detail and not ok else ""))


db = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)


def new_link(user_id, purpose, email, minutes=30):
    """Create a link token the way the API does (as the account, hash only). Returns the raw token."""
    raw = secrets.token_urlsafe(32)
    with db.cursor() as cur:
        cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', 'user', true)", (str(user_id),))
        cur.execute(
            "INSERT INTO account_tokens (user_id, purpose, email, token_hash, expires_at) "
            "VALUES (%s, %s, %s, %s, now() + make_interval(mins => %s))",
            (user_id, purpose, email, hashlib.sha256(raw.encode()).hexdigest(), minutes),
        )
    db.commit()
    return raw


def link_count(user_id, purpose):
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM account_tokens WHERE user_id = %s AND purpose = %s", (user_id, purpose))
        n = cur.fetchone()["n"]
    db.commit()
    return n


def register(username, **extra):
    s, b = call("POST", "/api/v1/auth/register", {"username": username, "password": PASSWORD, "email": f"{username}@example.test", **extra})
    if s == 201:
        cleanup[username] = (b["token"], PASSWORD)
    return s, b


print(f"Testing {BASE}  (run {RUN})")
carol, dave = f"t_carol_{RUN}", f"t_dave_{RUN}"
carol_email, dave_email = f"t_carol_{RUN}@example.com", f"t_dave_{RUN}@example.com"

# ----------------------------------------------------------------------
print("--- Forgot password")
s, b = call("POST", "/api/v1/auth/forgot-password", {"email": f"nobody_{RUN}@example.test"})
if s == 503:
    print("  The server cannot send email (set SMTP_* or MAIL_DEV_LOG=1). Stopping.")
    sys.exit(1)
generic = b
check("E-01", "unknown email -> 202 with the generic reply", s == 202 and "detail" in b, f"{s} {b}")

s, b = register(carol, email=carol_email.upper())
check("E-02", "sign up with an email -> 201, confirmation link sent", s == 201 and b.get("email_status") == "sent", f"{s} {b}")
carol_id, carol_token = (b["user"]["id"], b["token"]) if s == 201 else (None, None)
s2, b2 = call("GET", "/api/v1/me", token=carol_token)
check("E-03", "email is not saved until it is confirmed", s2 == 200 and b2["email"] is None, f"{s2} {b2}")

s, b = call("POST", "/api/v1/auth/forgot-password", {"email": carol})
check("E-04", "forgot by username -> 422 (a reset link needs an email)",
      s == 422 and link_count(carol_id, "reset_password") == 0, f"{s} {b}")
s, b = call("POST", "/api/v1/auth/forgot-password", {"email": carol_email})
check("E-23", "forgot by the sign-up email before it is confirmed -> same reply, reset link made",
      s == 202 and b == generic and link_count(carol_id, "reset_password") == 1, f"{s} {b}")

s, b = register(f"t_bad_{RUN}", email="not-an-email")
check("E-05", "sign up with a malformed email -> 422", s == 422, f"{s} {b}")
s, b = call("POST", "/api/v1/auth/register", {"username": f"t_noemail_{RUN}", "password": PASSWORD})
check("E-21", "sign up without an email -> 422", s == 422, f"{s} {b}")

# ----------------------------------------------------------------------
print("--- Confirm the recovery email")
s, b = call("POST", "/api/v1/auth/verify-email", {"token": "x" * 43})
check("E-06", "made-up confirmation token -> 400", s == 400, f"{s} {b}")

raw = new_link(carol_id, "verify_email", carol_email)
s, b = call("POST", "/api/v1/auth/verify-email", {"token": raw})
s2, b2 = call("GET", "/api/v1/me", token=carol_token)
check("E-07", "confirmation link saves the email (lowercase)",
      s == 200 and b2.get("email") == carol_email, f"{s} {b} / {b2}")
s, b = call("POST", "/api/v1/auth/verify-email", {"token": raw})
check("E-08", "the same confirmation link a second time -> 400", s == 400, f"{s} {b}")

s, b = call("POST", "/api/v1/me/email", {"email": carol_email}, token=carol_token)
check("E-09", "set the email you already have -> 400", s == 400, f"{s} {b}")

s, b = register(dave)
dave_id, dave_token = (b["user"]["id"], b["token"]) if s == 201 else (None, None)
s, b = call("POST", "/api/v1/me/email", {"email": carol_email}, token=dave_token)
check("E-10", "another account's email -> 409", s == 409, f"{s} {b}")
s, b = register(f"t_dup_{RUN}", email=carol_email.upper())
check("E-22", "sign up with an email another account confirmed -> 409", s == 409, f"{s} {b}")
s, b = call("POST", "/api/v1/me/email", {"email": dave_email}, token=dave_token)
check("E-11", "POST /me/email sends a second confirmation link -> 202",
      s == 202 and link_count(dave_id, "verify_email") == 2, f"{s} {b}")
s, b = call("POST", "/api/v1/me/email", {"email": dave_email})
check("E-12", "POST /me/email as a guest -> 401", s == 401, f"{s} {b}")

# ----------------------------------------------------------------------
print("--- Reset the password")
s, b = call("POST", "/api/v1/auth/forgot-password", {"login": carol_email.upper()})
check("E-13", "forgot by email (any letter case, old 'login' field) -> 202 and a reset link is made",
      s == 202 and link_count(carol_id, "reset_password") == 2, f"{s} {b}")
for _ in range(4):
    call("POST", "/api/v1/auth/forgot-password", {"email": carol_email})
check("E-14", "at most 3 reset emails per account per hour",
      link_count(carol_id, "reset_password") == 3, f"{link_count(carol_id, 'reset_password')} links")

s, b = call("POST", "/api/v1/auth/reset-password", {"token": "y" * 43, "new_password": "N3wPassw0rd"})
check("E-15", "made-up reset token -> 400", s == 400, f"{s} {b}")

expired = new_link(carol_id, "reset_password", carol_email, minutes=-1)
s, b = call("POST", "/api/v1/auth/reset-password", {"token": expired, "new_password": "N3wPassw0rd"})
check("E-16", "expired reset link -> 400", s == 400, f"{s} {b}")

raw = new_link(carol_id, "reset_password", carol_email)
s, b = call("POST", "/api/v1/auth/reset-password", {"token": raw, "new_password": "password"})
check("E-17", "weak new password -> 422 (link still usable)", s == 422, f"{s} {b}")

new_password = f"R3set{RUN}pass"
s, b = call("POST", "/api/v1/auth/reset-password", {"token": raw, "new_password": new_password})
ok = s == 200 and b.get("token") and b["user"]["username"] == carol
if ok:
    cleanup[carol] = (b["token"], new_password)
s_old, _ = call("GET", "/api/v1/me", token=carol_token)
s_login, _ = call("POST", "/api/v1/auth/login", {"username": carol, "password": new_password})
s_was, _ = call("POST", "/api/v1/auth/login", {"username": carol, "password": PASSWORD})
check("E-18", "reset works, logs in, signs out old tokens, old password stops working",
      ok and s_old == 401 and s_login == 200 and s_was == 401, f"{s} old={s_old} new={s_login} was={s_was}")

s, b = call("POST", "/api/v1/auth/reset-password", {"token": raw, "new_password": f"Again{RUN}9x"})
check("E-19", "the same reset link a second time -> 400", s == 400, f"{s} {b}")

with db.cursor() as cur:
    cur.execute("SELECT COUNT(*) AS n FROM account_tokens WHERE user_id = %s AND purpose = 'reset_password' "
                "AND used_at IS NULL AND expires_at > now()", (carol_id,))
    live = cur.fetchone()["n"]
db.commit()
check("E-20", "a successful reset retires the account's other reset links", live == 0, f"{live} still live")

erin = f"t_erin_{RUN}"
s, b = register(erin)
erin_id, erin_email = (b["user"]["id"], f"{erin}@example.test") if s == 201 else (None, None)
raw = new_link(erin_id, "reset_password", erin_email)
erin_password = f"Er1n{RUN}pass"
s, b = call("POST", "/api/v1/auth/reset-password", {"token": raw, "new_password": erin_password})
if s == 200:
    cleanup[erin] = (b["token"], erin_password)
s2, b2 = call("GET", "/api/v1/me", token=(b or {}).get("token"))
check("E-24", "a reset link sent to an unconfirmed sign-up email also confirms that email",
      s == 200 and s2 == 200 and b2.get("email") == erin_email, f"{s} {s2} {b2 and b2.get('email')}")

# ----------------------------------------------------------------------
print("--- Database rules (RLS) on account_tokens")
try:
    with db.cursor() as cur:
        cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', 'user', true)", (str(dave_id),))
        cur.execute("INSERT INTO account_tokens (user_id, purpose, email, token_hash, expires_at) "
                    "VALUES (%s, 'reset_password', 'x@example.com', %s, now() + interval '30 minutes')",
                    (carol_id, "0" * 64))
    db.commit()
    check("R-01", "cannot create a reset link for someone else's account", False, "insert was allowed")
except pg_errors.InsufficientPrivilege:
    db.rollback()
    check("R-01", "cannot create a reset link for someone else's account", True)

try:
    with db.cursor() as cur:
        cur.execute("UPDATE account_tokens SET expires_at = now() + interval '1 year' WHERE user_id = %s", (carol_id,))
    db.commit()
    check("R-02", "cannot extend a link's expiry (column privilege)", False, "update was allowed")
except pg_errors.InsufficientPrivilege:
    db.rollback()
    check("R-02", "cannot extend a link's expiry (column privilege)", True)

# ----------------------------------------------------------------------
print("--- Cleanup")
for username, (tok, pw) in list(cleanup.items()):
    s, _ = call("DELETE", "/api/v1/me", {"confirm": username, "password": pw}, token=tok)
    if s != 204:
        s2, b2 = call("POST", "/api/v1/auth/login", {"username": username, "password": pw})
        if s2 == 200:
            s, _ = call("DELETE", "/api/v1/me", {"confirm": username, "password": pw}, token=b2["token"])
    print(f"  deleted {username}: {'yes' if s == 204 else f'NO (HTTP {s}) - delete it in Neon'}")
db.close()

passed = sum(ok for _, ok in results)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

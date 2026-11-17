"""Tests for accounts, Google sign-in, profiles, comment editing and the database security rules.

    python tests/accounts_tests.py                      # against http://127.0.0.1:8000
    python tests/accounts_tests.py https://<site>       # against a deployment

Reads from .env / the environment:
    DATABASE_URL        lawliet_app connection, for the database-level RLS checks (R-xx)
    TEST_ADMIN_USERNAME / TEST_ADMIN_PASSWORD   optional; enables the admin checks
Creates its own throwaway accounts (prefix t_) and deletes them at the end. The test
law it creates as admin is deleted too. The one test note kept as "Deleted user" is
removed with SEED_DATABASE_URL (owner) when it is set. Nothing else is changed.
"""
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
RUN = secrets.token_hex(3)
PASSWORD = f"Passw0rd{RUN}"
results = []
cleanup_tokens = {}  # username -> (token, password)


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


def register(username, password=PASSWORD, **extra):
    status, body = call("POST", "/api/v1/auth/register", {"username": username, "password": password, **extra})
    if status == 201:
        cleanup_tokens[username] = (body["token"], password)
    return status, body


# ----------------------------------------------------------------------
print(f"Testing {BASE}  (run {RUN})\n--- Sign up and log in")
alice, bob, locky = f"t_alice_{RUN}", f"t_bob_{RUN}", f"t_lock_{RUN}"

s, b = register(alice, display_name="Alice Test")
check("A-01", "sign up with valid details -> 201 user", s == 201 and b["role"] == "user" and b["token"], f"{s} {b}")
alice_token = b["token"] if s == 201 else None

s, b = register(alice.upper())
check("A-02", "same username in other letter case -> 409", s == 409, f"{s} {b}")

s, b = register(f"t_weak_{RUN}", password="password")
check("A-03", "weak password (no number) -> 422", s == 422, f"{s} {b}")

s, b = register(f"t_root_{RUN}", role="admin")
check("A-04", "sign up asking for role admin -> 422", s == 422, f"{s} {b}")

s, b = register(f"bad name {RUN}")
check("A-05", "username with spaces -> 422", s == 422, f"{s} {b}")

s, b = call("POST", "/api/v1/auth/login", {"username": alice.upper(), "password": PASSWORD})
check("A-06", "login ignores username letter case", s == 200 and b["user"]["username"] == alice, f"{s} {b}")

register(locky)
codes = [call("POST", "/api/v1/auth/login", {"username": locky, "password": "WrongPass1"})[0] for _ in range(5)]
s, b = call("POST", "/api/v1/auth/login", {"username": locky, "password": PASSWORD})
check("A-07", "5 wrong passwords lock the account (correct one then -> 429)",
      codes == [401] * 5 and s == 429, f"{codes} then {s}")

s, b = call("POST", "/api/v1/auth/login", {"username": alice, "password": "x" * 100})
check("A-08", "password over 72 bytes -> 401, not 500", s == 401, f"{s} {b}")

s, b = call("GET", "/api/v1/auth/config")
check("A-09", "auth config is public", s == 200 and "google_client_id" in b, f"{s} {b}")

s, b = call("POST", "/api/v1/auth/google", {"credential": "x" * 40})
check("A-10", "fake Google credential is refused", s in (401, 503), f"{s} {b}")

# ----------------------------------------------------------------------
print("--- Profile settings")
s, b = call("GET", "/api/v1/me", token=alice_token)
check("P-01", "GET /me returns the profile without secrets",
      s == 200 and b["display_name"] == "Alice Test" and "password_hash" not in b and "google_sub" not in b,
      f"{s} {b}")

s, b = call("PATCH", "/api/v1/me", {"display_name": "Alice B.", "bio": "Law student", "theme": "light", "accent": "rose"},
            token=alice_token)
s2, b2 = call("GET", "/api/v1/me", token=alice_token)
check("P-02", "PATCH /me saves name, bio, theme and accent",
      s == 200 and (b2["display_name"], b2["bio"], b2["theme"], b2["accent"]) == ("Alice B.", "Law student", "light", "rose"),
      f"{s} {b2}")

s, b = call("PATCH", "/api/v1/me", {"role": "admin"}, token=alice_token)
check("P-03", "PATCH /me cannot change role -> 422", s == 422, f"{s} {b}")

s, b = call("PATCH", "/api/v1/me", {"theme": "purple"}, token=alice_token)
check("P-04", "unknown theme -> 422", s == 422, f"{s} {b}")

s, b = call("GET", "/api/v1/me")
check("P-05", "GET /me as a guest -> 401", s == 401, f"{s} {b}")

new_password = f"N3wPassw0rd{RUN}"
s, b = call("POST", "/api/v1/me/password", {"current_password": "WrongPass1", "new_password": new_password}, token=alice_token)
check("P-06", "change password with the wrong current one -> 400", s == 400, f"{s} {b}")

old_token = alice_token
s, b = call("POST", "/api/v1/me/password", {"current_password": PASSWORD, "new_password": new_password}, token=alice_token)
ok = s == 200 and b.get("token")
if ok:
    alice_token = b["token"]
    cleanup_tokens[alice] = (alice_token, new_password)
s2, _ = call("GET", "/api/v1/me", token=old_token)
check("P-07", "password change returns a new token and signs out the old one", ok and s2 == 401, f"{s} then old token {s2}")

# ----------------------------------------------------------------------
print("--- Log out of all devices")
s, b = register(bob)
bob_token = b["token"] if s == 201 else None
s, b = call("POST", "/api/v1/auth/login", {"username": bob, "password": PASSWORD})
bob_second = b["token"] if s == 200 else None
s, _ = call("POST", "/api/v1/auth/logout-all", token=bob_token)
s1, _ = call("GET", "/api/v1/me", token=bob_token)
s2, _ = call("GET", "/api/v1/me", token=bob_second)
check("L-01", "log out everywhere -> both of bob's tokens stop working", s == 204 and s1 == 401 and s2 == 401, f"{s} {s1} {s2}")
s, b = call("POST", "/api/v1/auth/login", {"username": bob, "password": PASSWORD})
bob_token = b["token"] if s == 200 else None
cleanup_tokens[bob] = (bob_token, PASSWORD)

# ----------------------------------------------------------------------
print("--- Edit comments")
s, b = call("POST", "/api/v1/laws/1/comments", {"user_name": "Alice B.", "comment": f"Test note {RUN}"}, token=alice_token)
note = next((n for n in (b or {}).get("comments", []) if n["comment"] == f"Test note {RUN}"), None) if s == 201 else None
check("C-01", "posting a note returns its id and author id", note is not None and note.get("user_id") is not None, f"{s}")
note_id = note["id"] if note else 0

s, b = call("PATCH", f"/api/v1/comments/{note_id}", {"comment": f"Edited note {RUN}"}, token=alice_token)
edited = next((n for n in (b or {}).get("comments", []) if n["id"] == note_id), None) if s == 200 else None
check("C-02", "author edits own note -> 200, text changed, edited_at set",
      edited is not None and edited["comment"] == f"Edited note {RUN}" and edited["edited_at"], f"{s} {b}")

s, b = call("PATCH", f"/api/v1/comments/{note_id}", {"comment": "hijacked"}, token=bob_token)
check("C-03", "another user edits it -> 403", s == 403, f"{s} {b}")

s, b = call("PATCH", f"/api/v1/comments/{note_id}", {"comment": "hijacked"})
check("C-04", "a guest edits it -> 401", s == 401, f"{s} {b}")

s, b = call("PATCH", "/api/v1/comments/99999999", {"comment": "x"}, token=alice_token)
check("C-05", "editing a note that does not exist -> 404", s == 404, f"{s} {b}")

s, b = call("PATCH", f"/api/v1/comments/{note_id}", {"comment": "   "}, token=alice_token)
check("C-06", "blank note text -> 422", s == 422, f"{s} {b}")

# ----------------------------------------------------------------------
print("--- Delete account")
s, b = call("DELETE", "/api/v1/me", {"confirm": "someone-else", "password": new_password}, token=alice_token)
check("D-01", "wrong confirmation -> 400", s == 400, f"{s} {b}")

s, b = call("DELETE", "/api/v1/me", {"confirm": alice, "password": "WrongPass1"}, token=alice_token)
check("D-02", "wrong password -> 400", s == 400, f"{s} {b}")

s, b = call("DELETE", "/api/v1/me", {"confirm": alice, "password": new_password}, token=alice_token)
s2, _ = call("GET", "/api/v1/me", token=alice_token)
check("D-03", "delete own account -> 204 and its token stops working", s == 204 and s2 == 401, f"{s} then {s2}")
if s == 204:
    cleanup_tokens.pop(alice, None)

s, b = call("GET", "/api/v1/laws/1", token=bob_token)
kept = next((n for n in (b or {}).get("user_notes", []) if n["id"] == note_id), None) if s == 200 else None
check("D-04", "the deleted user's note stays, shown as 'Deleted user'",
      kept is not None and kept["user_name"] == "Deleted user" and kept["user_id"] is None, f"{kept}")

s, b = call("POST", "/api/v1/auth/login", {"username": alice, "password": new_password})
check("D-05", "the deleted account can no longer log in", s == 401, f"{s} {b}")

# ----------------------------------------------------------------------
admin_user, admin_pw = os.environ.get("TEST_ADMIN_USERNAME"), os.environ.get("TEST_ADMIN_PASSWORD")
if admin_user and admin_pw:
    print("--- Admin still works under the security rules")
    s, b = call("POST", "/api/v1/auth/login", {"username": admin_user, "password": admin_pw})
    admin_token = b["token"] if s == 200 else None
    law = {
        "ra_number": f"RA 9{RUN[:4]}", "official_title": "TEST ONLY accounts test law",
        "plain_title": "TEST ONLY law", "category": "Environment", "year": 2026,
        "reading_time_minutes": 1, "importance_rating": 1, "tldr_summary": "Test law, delete me.",
        "full_breakdown": "Test law, delete me.", "why_it_matters": "Test.",
        "example_scenario": "Test law, delete me.", "penalties": "None.", "min_fine_php": 0,
        "total_sections": 1, "enacting_president": "Test", "target_audience": "Testers",
        "source_url": "https://example.com/test",
    }
    s1, b1 = call("POST", "/api/v1/laws", law, token=admin_token)
    law_id = b1["id"] if s1 == 201 else 0
    s2, _ = call("PATCH", f"/api/v1/laws/{law_id}", {"min_fine_php": 5000}, token=admin_token)
    s3, _ = call("DELETE", f"/api/v1/laws/{law_id}", token=admin_token)
    check("M-01", "admin create / update / delete a law -> 201 / 200 / 204", (s1, s2, s3) == (201, 200, 204), f"{s1} {s2} {s3}")
    s, b = call("DELETE", "/api/v1/me", {"confirm": admin_user, "password": admin_pw}, token=admin_token)
    check("M-02", "the only admin cannot delete their account -> 409", s == 409, f"{s} {b}")
else:
    print("--- Admin checks skipped (set TEST_ADMIN_USERNAME and TEST_ADMIN_PASSWORD to run them)")

# ----------------------------------------------------------------------
print("--- Database security rules (connects as lawliet_app, no API in between)")
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("  skipped: DATABASE_URL not set")
else:
    import psycopg2
    from psycopg2 import errors as pg_errors

    conn = psycopg2.connect(db_url)
    conn.autocommit = False

    def attempt(sql, params=(), user_id="", role="guest"):
        """Run one statement as lawliet_app acting as user_id/role, then roll back.
        Returns 'denied', or the number of rows changed."""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', %s, true)",
                            (str(user_id), role))
                cur.execute(sql, params)
                return cur.rowcount
        except pg_errors.InsufficientPrivilege:
            return "denied"
        finally:
            conn.rollback()

    with conn.cursor() as cur:
        cur.execute("SELECT bool_and(rowsecurity) FROM pg_tables WHERE tablename IN ('laws','comments','users')")
        rls_on = cur.fetchone()[0]
        cur.execute("SELECT id FROM users WHERE username = %s", (bob,))
        bob_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM comments WHERE user_id IS DISTINCT FROM %s ORDER BY id LIMIT 1", (bob_id,))
        other_comment = cur.fetchone()[0]
    conn.rollback()

    if not rls_on:
        print("  skipped: RLS is not enabled yet (run scripts/migrate_003_security_rules.sql)")
    else:
        r = attempt("UPDATE laws SET min_fine_php = min_fine_php WHERE id = 1", user_id=bob_id, role="user")
        check("R-01", "a user cannot change a law, even straight in SQL (0 rows)", r == 0, r)
        r = attempt("INSERT INTO laws (ra_number) VALUES ('RA 0')", user_id=bob_id, role="user")
        check("R-02", "a user cannot insert a law (policy refuses)", r == "denied", r)
        r = attempt("UPDATE comments SET comment = 'hijacked' WHERE id = %s", (other_comment,), user_id=bob_id, role="user")
        check("R-03", "a user cannot edit someone else's comment (0 rows)", r == 0, r)
        r = attempt("INSERT INTO comments (law_id, user_id, user_name, comment) VALUES (1, %s, 'x', 'x')",
                    (bob_id + 1,), user_id=bob_id, role="user")
        check("R-04", "a user cannot post a comment as someone else", r == "denied", r)
        r = attempt("UPDATE users SET role = 'admin' WHERE id = %s", (bob_id,), user_id=bob_id, role="user")
        check("R-05", "nobody can change a role through lawliet_app (column privilege)", r == "denied", r)
        r = attempt("INSERT INTO users (username, password_hash, role) VALUES ('t_x', 'x', 'admin')")
        check("R-06", "a new account cannot be created as admin", r == "denied", r)
        r = attempt("DELETE FROM users WHERE id <> %s", (bob_id,), user_id=bob_id, role="user")
        check("R-07", "a user cannot delete other accounts (0 rows)", r == 0, r)
        r = attempt("UPDATE users SET bio = 'x' WHERE id = %s", (bob_id,), user_id=bob_id, role="user")
        check("R-08", "a user can still change their own profile (1 row)", r == 1, r)
    conn.close()

# ----------------------------------------------------------------------
print("--- Google sign-in token checks (offline, with a test key)")
try:
    from datetime import datetime, timedelta, timezone

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    import _auth

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class FakeKey:
        def __init__(self, k):
            self.key = k

    _auth._google_keys.get_signing_key_from_jwt = lambda token: FakeKey(key.public_key())
    os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
    now = datetime.now(timezone.utc)

    def token(**over):
        claims = {"iss": "https://accounts.google.com", "aud": "test-client.apps.googleusercontent.com",
                  "sub": "1234567890", "email": "juan@gmail.com", "email_verified": True,
                  "name": "Juan", "iat": now, "exp": now + timedelta(minutes=5), **over}
        return jwt.encode(claims, key, algorithm="RS256")

    def verdict(t):
        try:
            _auth.verify_google_credential(t)
            return "ok"
        except Exception as exc:  # HTTPException
            return getattr(exc, "status_code", repr(exc))

    check("G-01", "valid Google token is accepted", verdict(token()) == "ok")
    check("G-02", "token for another site's client ID is refused", verdict(token(aud="someone-else")) == 401)
    check("G-03", "token from another issuer is refused", verdict(token(iss="https://evil.example")) == 401)
    check("G-04", "unverified email is refused", verdict(token(email_verified=False)) == 401)
    check("G-05", "expired token is refused", verdict(token(exp=now - timedelta(minutes=5))) == 401)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode({"iss": "https://accounts.google.com", "aud": "test-client.apps.googleusercontent.com",
                         "sub": "1", "email": "x@gmail.com", "email_verified": True,
                         "iat": now, "exp": now + timedelta(minutes=5)}, other, algorithm="RS256")
    check("G-06", "token signed by a different key is refused", verdict(forged) == 401)
except ImportError as exc:
    print(f"  skipped: {exc}")

# ----------------------------------------------------------------------
print("--- Cleanup")
for username, (tok, pw) in list(cleanup_tokens.items()):
    s, _ = call("DELETE", "/api/v1/me", {"confirm": username, "password": pw}, token=tok)
    if s != 204:  # token may be stale (e.g. after a lockout); log in again
        s2, b2 = call("POST", "/api/v1/auth/login", {"username": username, "password": pw})
        if s2 == 200:
            s, _ = call("DELETE", "/api/v1/me", {"confirm": username, "password": pw}, token=b2["token"])
    print(f"  deleted {username}: {'yes' if s == 204 else f'NO (HTTP {s}) - delete it in Neon'}")

# The delete-account test leaves its note on law 1 as "Deleted user" (that is the feature).
# lawliet_app may not delete comments, so the owner connection removes it if it is set.
owner_url = os.environ.get("SEED_DATABASE_URL")
leftover = f"Edited note {RUN}"
if owner_url:
    import psycopg2
    with psycopg2.connect(owner_url) as owner, owner.cursor() as cur:
        cur.execute("DELETE FROM comments WHERE comment = %s AND user_id IS NULL", (leftover,))
        print(f"  removed {cur.rowcount} leftover test note(s)")
else:
    print("  SEED_DATABASE_URL not set: remove the test note in the Neon SQL Editor with")
    print(f"  DELETE FROM comments WHERE comment = '{leftover}' AND user_id IS NULL;")

passed = sum(ok for _, ok in results)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

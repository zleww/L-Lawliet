"""Tests for saved laws, ratings, helpful votes, note reports, law suggestions, public profiles
and admin account management (migration 005).

    python tests/features_tests.py                      # against http://127.0.0.1:8000
    python tests/features_tests.py https://<site>       # against a deployment

Reads from .env / the environment:
    DATABASE_URL        lawliet_app connection, for the database-level RLS checks (R-xx)
    SEED_DATABASE_URL   owner connection, only to remove the test rows at the end
    TEST_ADMIN_USERNAME / TEST_ADMIN_PASSWORD   optional; enables the admin checks (AD-xx)
Creates throwaway accounts (prefix t_) and deletes them at the end.
"""
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

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
RUN = secrets.token_hex(3)
PASSWORD = f"Passw0rd{RUN}"
RA_A = f"RA {90000 + secrets.randbelow(9999)}"   # law numbers that do not exist yet
RA_B = f"RA {80000 + secrets.randbelow(9999)}"
results, accounts, created_laws = [], {}, []


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


def new_account(prefix, display=None):
    username = f"t_{prefix}_{RUN}"
    body = {"username": username, "password": PASSWORD}
    if display:
        body["display_name"] = display
    s, b = call("POST", "/api/v1/auth/register", body)
    if s != 201:
        sys.exit(f"Could not create {username}: {s} {b}")
    accounts[username] = b["token"]
    return username, b["token"], b["user"]["id"]


def login(username):
    s, b = call("POST", "/api/v1/auth/login", {"username": username, "password": PASSWORD})
    if s == 200:
        accounts[username] = b["token"]
        return b["token"]
    return None


print(f"Testing {BASE}  (run {RUN})")
ann, ann_t, ann_id = new_account("ann", "Ann Test")
ben, ben_t, ben_id = new_account("ben", "Ben Test")

# ----------------------------------------------------------------------
print("--- Saved laws")
s, b = call("POST", "/api/v1/laws/1/save", token=ann_t)
check("SV-01", "save law 1 -> 201", s == 201 and b["saved"], f"{s} {b}")
s, b = call("POST", "/api/v1/laws/1/save", token=ann_t)
check("SV-02", "save it again -> 409", s == 409, f"{s} {b}")
s, b = call("GET", "/api/v1/me/saved", token=ann_t)
check("SV-03", "My saved laws lists it", s == 200 and any(x["id"] == 1 for x in b["saved"]), f"{s} {b}")
s, b = call("GET", "/api/v1/laws/1", token=ann_t)
check("SV-04", "law 1 says saved: true for ann", s == 200 and b.get("saved") is True, f"{s} {b.get('saved')}")
s, b = call("GET", "/api/v1/me/saved", token=ben_t)
check("SV-05", "ben's saved list does not show ann's save", s == 200 and b["count"] == 0, f"{s} {b}")
s, b = call("POST", "/api/v1/laws/99999999/save", token=ann_t)
check("SV-06", "save a law that does not exist -> 404", s == 404, f"{s} {b}")
s, b = call("POST", "/api/v1/laws/1/save")
check("SV-07", "a guest saves -> 401", s == 401, f"{s} {b}")
s1, _ = call("DELETE", "/api/v1/laws/1/save", token=ann_t)
s2, b2 = call("DELETE", "/api/v1/laws/1/save", token=ann_t)
check("SV-08", "remove -> 204, remove again -> 404", (s1, s2) == (204, 404), f"{s1} {s2} {b2}")

# ----------------------------------------------------------------------
print("--- Ratings")
s, b = call("PUT", "/api/v1/laws/2/rating", {"rating": 4}, ann_t)
check("RT-01", "ann rates law 2 a 4 -> 200", s == 200 and b["my_rating"] == 4 and b["rating_count"] >= 1, f"{s} {b}")
base_count = b["rating_count"] - 1 if s == 200 else 0
s, b = call("PUT", "/api/v1/laws/2/rating", {"rating": 2}, ben_t)
check("RT-02", "ben rates it a 2 -> count +1", s == 200 and b["rating_count"] == base_count + 2, f"{s} {b}")
s, b = call("PUT", "/api/v1/laws/2/rating", {"rating": 5}, ann_t)
check("RT-03", "ann rates again -> her rating changes, count stays", s == 200 and b["my_rating"] == 5
      and b["rating_count"] == base_count + 2, f"{s} {b}")
s, b = call("PUT", "/api/v1/laws/2/rating", {"rating": 6}, ann_t)
check("RT-04", "rating 6 -> 422", s == 422, f"{s} {b}")
s, b = call("PUT", "/api/v1/laws/99999999/rating", {"rating": 3}, ann_t)
check("RT-05", "rate a law that does not exist -> 404", s == 404, f"{s} {b}")
s, b = call("GET", "/api/v1/laws/2")
check("RT-06", "guests see the average but no personal rating",
      s == 200 and b["rating_count"] == base_count + 2 and "my_rating" not in b, f"{s} {b.get('rating_count')}")
s1, _ = call("DELETE", "/api/v1/laws/2/rating", token=ben_t)
s2, b2 = call("DELETE", "/api/v1/laws/2/rating", token=ben_t)
check("RT-07", "remove rating -> 204, again -> 404", (s1, s2) == (204, 404), f"{s1} {s2} {b2}")

# ----------------------------------------------------------------------
print("--- Helpful votes")
s, b = call("POST", "/api/v1/laws/1/comments", {"user_name": "Ann Test", "comment": f"Feature test note {RUN}"}, ann_t)
note = next((n for n in (b or {}).get("comments", []) if n["comment"] == f"Feature test note {RUN}"), None)
note_id = note["id"] if note else 0
s, b = call("POST", f"/api/v1/comments/{note_id}/vote", token=ben_t)
check("VT-01", "ben marks ann's note helpful -> 201, count 1", s == 201 and b["helpful_count"] == 1, f"{s} {b}")
s, b = call("POST", f"/api/v1/comments/{note_id}/vote", token=ben_t)
check("VT-02", "vote again -> 409", s == 409, f"{s} {b}")
s, b = call("POST", f"/api/v1/comments/{note_id}/vote", token=ann_t)
check("VT-03", "ann votes on her own note -> 403", s == 403, f"{s} {b}")
s, b = call("GET", "/api/v1/laws/1", token=ben_t)
mine = next((n for n in (b or {}).get("user_notes", []) if n["id"] == note_id), {})
check("VT-04", "ben sees voted_by_me and helpful_count 1", mine.get("voted_by_me") is True and mine.get("helpful_count") == 1, mine)
counts = [n["helpful_count"] for n in (b or {}).get("user_notes", [])]
check("VT-05", "notes are ordered most helpful first", counts == sorted(counts, reverse=True), counts)
s1, _ = call("DELETE", f"/api/v1/comments/{note_id}/vote", token=ben_t)
s2, b2 = call("DELETE", f"/api/v1/comments/{note_id}/vote", token=ben_t)
check("VT-06", "remove vote -> 204, again -> 404", (s1, s2) == (204, 404), f"{s1} {s2} {b2}")
s, b = call("POST", "/api/v1/comments/99999999/vote", token=ben_t)
check("VT-07", "vote on a note that does not exist -> 404", s == 404, f"{s} {b}")

# ----------------------------------------------------------------------
print("--- Reports")
s, b = call("POST", f"/api/v1/comments/{note_id}/report", {"reason": "spam", "details": f"test {RUN}"}, ben_t)
check("RP-01", "ben reports ann's note -> 201", s == 201, f"{s} {b}")
report_id = b.get("report_id") if s == 201 else 0
s, b = call("POST", f"/api/v1/comments/{note_id}/report", {"reason": "other"}, ben_t)
check("RP-02", "report it again -> 409", s == 409, f"{s} {b}")
s, b = call("POST", f"/api/v1/comments/{note_id}/report", {"reason": "spam"}, ann_t)
check("RP-03", "ann reports her own note -> 403", s == 403, f"{s} {b}")
s, b = call("POST", f"/api/v1/comments/{note_id}/report", {"reason": "boring"}, ann_t)
check("RP-04", "unknown reason -> 422", s == 422, f"{s} {b}")
s, b = call("GET", "/api/v1/admin/reports", token=ben_t)
check("RP-05", "a user opens the admin report queue -> 403", s == 403, f"{s} {b}")

# ----------------------------------------------------------------------
print("--- Law suggestions")
ra_digits = RA_A.split()[1]
s, b = call("POST", "/api/v1/suggestions", {"ra_number": f"R.A. No. {ra_digits}", "title": "Test suggested law",
                                            "reason": f"Feature test suggestion {RUN}"}, ann_t)
check("SG-01", "suggest a law (RA number written any way) -> 201 pending",
      s == 201 and b["status"] == "pending" and b["ra_number"] == RA_A, f"{s} {b}")
sug_a = b.get("id") if s == 201 else 0
s, b = call("POST", "/api/v1/suggestions", {"ra_number": RA_A, "title": "Again", "reason": "Same law again please"}, ann_t)
check("SG-02", "suggest the same RA again while pending -> 409", s == 409, f"{s} {b}")
s, b = call("POST", "/api/v1/suggestions", {"ra_number": "10175", "title": "Cybercrime", "reason": "Already exists here"}, ann_t)
check("SG-03", "suggest a law that is already in L-Lawliet -> 409", s == 409, f"{s} {b}")
s, b = call("POST", "/api/v1/suggestions", {"ra_number": "abc", "title": "Bad", "reason": "short"}, ann_t)
check("SG-04", "bad RA number and too-short reason -> 422", s == 422, f"{s} {b}")
s, b = call("GET", "/api/v1/me/suggestions", token=ann_t)
check("SG-05", "ann sees her pending suggestion", s == 200 and any(x["id"] == sug_a for x in b["suggestions"]), f"{s} {b}")
s, b = call("GET", "/api/v1/me/suggestions", token=ben_t)
check("SG-06", "ben does not see ann's suggestions", s == 200 and b["count"] == 0, f"{s} {b}")
s, b = call("PATCH", f"/api/v1/admin/suggestions/{sug_a}", {"status": "rejected"}, ann_t)
check("SG-07", "a user reviews a suggestion -> 403", s == 403, f"{s} {b}")

# ----------------------------------------------------------------------
print("--- Public profiles")
s, b = call("GET", f"/api/v1/users/{ann_id}", token=ben_t)
check("PF-01", "ben opens ann's profile: name, bio, notes; no email or settings",
      s == 200 and b["display_name"] == "Ann Test" and b["note_count"] == 1
      and not {"email", "theme", "password_hash", "token_version"} & set(b), f"{s} {b}")
s, b = call("GET", f"/api/v1/users/{ann_id}")
check("PF-02", "a guest opens a profile -> 401", s == 401, f"{s} {b}")
s, b = call("GET", "/api/v1/users/99999999", token=ben_t)
check("PF-03", "a profile that does not exist -> 404", s == 404, f"{s} {b}")

# ----------------------------------------------------------------------
admin_user, admin_pw = os.environ.get("TEST_ADMIN_USERNAME"), os.environ.get("TEST_ADMIN_PASSWORD")
if admin_user and admin_pw:
    print("--- Admin")
    s, b = call("POST", "/api/v1/auth/login", {"username": admin_user, "password": admin_pw})
    adm, adm_id = (b["token"], b["user"]["id"]) if s == 200 else (None, 0)

    s, b = call("GET", "/api/v1/admin/reports", token=adm)
    check("AD-01", "admin sees ben's report in the open queue", s == 200 and any(r["id"] == report_id for r in b["reports"]), f"{s}")
    s, b = call("PATCH", f"/api/v1/admin/reports/{report_id}", {"status": "dismissed"}, adm)
    s2, b2 = call("GET", "/api/v1/admin/reports?status=dismissed", token=adm)
    check("AD-02", "admin dismisses it -> it moves to the dismissed list",
          s == 200 and any(r["id"] == report_id for r in b2.get("reports", [])), f"{s} {b}")

    s, b = call("PATCH", f"/api/v1/admin/suggestions/{sug_a}", {"status": "approved"}, adm)
    check("AD-03", "approve without law_id -> 422", s == 422, f"{s} {b}")
    s, b = call("PATCH", f"/api/v1/admin/suggestions/{sug_a}", {"status": "rejected", "admin_note": "Test only"}, adm)
    s2, b2 = call("PATCH", f"/api/v1/admin/suggestions/{sug_a}", {"status": "rejected"}, adm)
    check("AD-04", "reject with a note -> 200; reviewing again -> 409",
          s == 200 and b["status"] == "rejected" and s2 == 409, f"{s} {b} {s2}")

    s, b = call("POST", "/api/v1/suggestions", {"ra_number": RA_B, "title": "Second test law",
                                                "reason": f"Feature test approval {RUN}"}, ben_t)
    sug_b = b.get("id") if s == 201 else 0
    law = {"ra_number": RA_B, "official_title": "TEST ONLY suggested law", "plain_title": "TEST ONLY suggested law",
           "category": "Environment", "year": 2026, "reading_time_minutes": 1, "importance_rating": 1,
           "tldr_summary": "Test law, delete me.", "full_breakdown": "Test law, delete me.", "why_it_matters": "Test.",
           "example_scenario": "Test law, delete me.", "penalties": "None.", "min_fine_php": 0, "total_sections": 1,
           "enacting_president": "Test", "target_audience": "Testers", "source_url": "https://example.com/test"}
    s1, b1 = call("POST", "/api/v1/laws", law, adm)
    law_b = b1.get("id") if s1 == 201 else 0
    created_laws.append(law_b)
    s, b = call("PATCH", f"/api/v1/admin/suggestions/{sug_b}", {"status": "approved", "law_id": law_b}, adm)
    s2, b2 = call("GET", "/api/v1/me/suggestions", token=ben_t)
    mine = next((x for x in b2.get("suggestions", []) if x["id"] == sug_b), {})
    check("AD-05", "admin adds the law, approves the suggestion; ben sees approved + law_id",
          s == 200 and mine.get("status") == "approved" and mine.get("law_id") == law_b, f"{s} {b} {mine}")

    s, b = call("GET", "/api/v1/admin/users", token=adm)
    check("AD-06", "admin user list shows the test accounts", s == 200 and any(u["username"] == ann for u in b["users"]), f"{s}")

    cara, cara_t, cara_id = new_account("cara")
    for _ in range(5):
        call("POST", "/api/v1/auth/login", {"username": cara, "password": "WrongPass1"})
    locked, _ = call("POST", "/api/v1/auth/login", {"username": cara, "password": PASSWORD})
    s, b = call("POST", f"/api/v1/admin/users/{cara_id}/unlock", token=adm)
    after = login(cara)
    check("AD-07", "locked account (429) -> admin unlocks -> login works", locked == 429 and s == 200 and after, f"{locked} {s} {after}")

    s, _ = call("POST", f"/api/v1/admin/users/{ben_id}/logout-all", token=adm)
    s2, _ = call("GET", "/api/v1/me", token=ben_t)
    check("AD-08", "admin logs ben out everywhere -> ben's token stops working", s == 204 and s2 == 401, f"{s} {s2}")
    ben_t = login(ben)

    s, b = call("DELETE", f"/api/v1/admin/users/{adm_id}", token=adm)
    check("AD-09", "admin deletes an admin account -> 403", s == 403, f"{s} {b}")
    s, b = call("DELETE", f"/api/v1/admin/users/{cara_id}", token=adm)
    s2, _ = call("POST", "/api/v1/auth/login", {"username": cara, "password": PASSWORD})
    check("AD-10", "admin deletes a user account -> 204, it can no longer log in", s == 204 and s2 == 401, f"{s} {s2}")
    if s == 204:
        accounts.pop(cara, None)
    s, b = call("DELETE", f"/api/v1/admin/users/{ann_id}", token=ben_t)
    check("AD-11", "a user calls the admin delete -> 403", s == 403, f"{s} {b}")

    for law_id in created_laws:
        call("DELETE", f"/api/v1/laws/{law_id}", token=adm)
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

    call("POST", "/api/v1/laws/3/save", token=ben_t)
    call("PUT", "/api/v1/laws/3/rating", {"rating": 3}, ben_t)
    conn = psycopg2.connect(db_url)

    def attempt(sql, params=(), user_id="", role="guest", fetch=False):
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', %s, true)",
                            (str(user_id), role))
                cur.execute(sql, params)
                return cur.fetchone()[0] if fetch else cur.rowcount
        except pg_errors.InsufficientPrivilege:
            return "denied"
        finally:
            conn.rollback()

    r = attempt("SELECT COUNT(*) FROM saved_laws WHERE user_id = %s", (ben_id,), ann_id, "user", fetch=True)
    check("R-11", "ann cannot read ben's saved laws in SQL (sees 0)", r == 0, r)
    r = attempt("INSERT INTO saved_laws (user_id, law_id) VALUES (%s, 4)", (ben_id,), ann_id, "user")
    check("R-12", "ann cannot save a law as ben", r == "denied", r)
    r = attempt("UPDATE law_ratings SET rating = 1 WHERE user_id = %s", (ben_id,), ann_id, "user")
    check("R-13", "ann cannot change ben's rating (0 rows)", r == 0, r)
    r = attempt("SELECT COUNT(*) FROM comment_reports", (), ann_id, "user", fetch=True)
    r_admin = attempt("SELECT COUNT(*) FROM comment_reports", (), 0, "admin", fetch=True)
    check("R-14", "a user cannot read other people's reports; an admin can", r == 0 and r_admin >= 1, f"{r} {r_admin}")
    r = attempt("INSERT INTO law_suggestions (user_id, ra_number, title, reason, status) "
                "VALUES (%s, 'RA 1', 'x title', 'self approved row', 'approved')", (ann_id,), ann_id, "user")
    check("R-15", "a user cannot insert a suggestion that is already approved", r == "denied", r)
    r = attempt("UPDATE law_suggestions SET status = 'approved'", (), ann_id, "user")
    check("R-16", "a user cannot review suggestions (0 rows)", r == 0, r)
    r = attempt("DELETE FROM users WHERE role = 'admin'", (), 0, "admin")
    check("R-17", "even an admin cannot delete an admin account in SQL (0 rows)", r == 0, r)
    r = attempt("UPDATE users SET role = 'admin' WHERE id = %s", (ann_id,), 0, "admin")
    check("R-18", "even an admin cannot change roles through lawliet_app", r == "denied", r)
    conn.close()

# ----------------------------------------------------------------------
print("--- Cleanup")
for username, tok in list(accounts.items()):
    tok = login(username) or tok
    s, _ = call("DELETE", "/api/v1/me", {"confirm": username, "password": PASSWORD}, tok)
    print(f"  deleted {username}: {'yes' if s == 204 else f'NO (HTTP {s})'}")
owner_url = os.environ.get("SEED_DATABASE_URL")
if owner_url:
    import psycopg2
    with psycopg2.connect(owner_url) as owner, owner.cursor() as cur:
        cur.execute("DELETE FROM comments WHERE comment = %s", (f"Feature test note {RUN}",))
        notes = cur.rowcount
        cur.execute("DELETE FROM law_suggestions WHERE ra_number IN (%s, %s)", (RA_A, RA_B))
        print(f"  removed {notes} test note(s) and {cur.rowcount} test suggestion(s)")
else:
    print("  SEED_DATABASE_URL not set: remove the test rows in the Neon SQL Editor with")
    print(f"  DELETE FROM comments WHERE comment = 'Feature test note {RUN}';")
    print(f"  DELETE FROM law_suggestions WHERE ra_number IN ('{RA_A}', '{RA_B}');")

passed = sum(ok for _, ok in results)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

"""Tests for the JustGiveupATP game endpoints (/api/v1/arena/*) and the admin game overview.

    python tests/arena_tests.py                      # against http://127.0.0.1:8000
    python tests/arena_tests.py https://<site>       # against a deployment

Creates two throwaway accounts (prefix g_) and deletes them at the end, which also deletes
their results and settings (ON DELETE CASCADE).
Reads from .env / the environment:
    DATABASE_URL        lawliet_app connection, for the database-level RLS checks
    TEST_ADMIN_USERNAME / TEST_ADMIN_PASSWORD   optional; enables the admin checks
    TEST_ARENA_ORIGIN   site to check CORS for (default https://just-give-up-atp.vercel.app)
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
results = []


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


def register(username):
    status, body = call("POST", "/api/v1/auth/register",
                        {"username": username, "password": PASSWORD, "display_name": f"Tester {username[-3:]}"})
    if status != 201:
        sys.exit(f"could not create {username}: {status} {body}")
    return body["token"], body["user"]["id"]


def result(case_id="bureaucratic-delay", tier=1, won=True, turns=4, jp_left=80):
    return {"case_id": case_id, "tier": tier, "won": won, "turns": turns, "jp_left": jp_left}


print(f"Testing {BASE}  (run {RUN})")
amy, amy_id = register(f"g_a{RUN}")
ben, ben_id = register(f"g_b{RUN}")

try:
    print("--- Guests")
    status, _ = call("GET", "/api/v1/arena/me")
    check("G-01", "guest has no saved record -> 401", status == 401, status)
    status, _ = call("POST", "/api/v1/arena/results", result())
    check("G-02", "guest results are not saved -> 401", status == 401, status)
    status, body = call("GET", "/api/v1/arena/leaderboard")
    check("G-03", "leaderboard is public", status == 200 and "players" in body, status)

    print("--- Saving results")
    status, body = call("POST", "/api/v1/arena/results", result(), amy)
    check("R-01", "save a win -> 201", status == 201 and body["won"] is True, body)
    call("POST", "/api/v1/arena/results", result(turns=3, jp_left=90), amy)
    call("POST", "/api/v1/arena/results", result("digital-intruder", 2, won=False, turns=9, jp_left=0), amy)
    call("POST", "/api/v1/arena/results", result("digital-intruder", 2, turns=7, jp_left=40), amy)
    status, me = call("GET", "/api/v1/arena/me", token=amy)
    won = {c["case_id"]: c for c in me["cases_won"]} if status == 200 else {}
    check("R-02", "record: 2 different cases won", status == 200 and set(won) == {"bureaucratic-delay", "digital-intruder"}, me)
    check("R-03", "record: 4 trials, 3 wins", status == 200 and me["trials"] == 4 and me["wins"] == 3, me)
    check("R-04", "best result per case", won.get("bureaucratic-delay", {}).get("best_turns") == 3
          and won["bureaucratic-delay"]["best_jp"] == 90, won)
    check("R-05", "history newest first", status == 200 and me["history"][0]["case_id"] == "digital-intruder"
          and me["history"][0]["won"] is True, me.get("history"))
    status, me_b = call("GET", "/api/v1/arena/me", token=ben)
    check("R-06", "another player starts empty", status == 200 and me_b["trials"] == 0, me_b)

    print("--- Validation")
    for test_id, bad, why in [
        ("V-01", result(case_id="Bad Case!"), "case id with spaces"),
        ("V-02", result(tier=4), "tier 4"),
        ("V-03", result(turns=-1), "negative turns"),
        ("V-04", result(jp_left=5000), "jp above 1000"),
        ("V-05", {**result(), "user_id": ben_id}, "extra field user_id"),
    ]:
        status, _ = call("POST", "/api/v1/arena/results", bad, amy)
        check(test_id, f"{why} -> 422", status == 422, status)

    print("--- Settings")
    status, body = call("GET", "/api/v1/arena/prefs", token=amy)
    check("S-01", "defaults", status == 200 and body == {"confirm_abandon": True, "reduce_motion": False, "hide_won": False}, body)
    status, body = call("PATCH", "/api/v1/arena/prefs", {"reduce_motion": True}, amy)
    check("S-02", "partial update", status == 200 and body["reduce_motion"] is True and body["confirm_abandon"] is True, body)
    status, _ = call("PATCH", "/api/v1/arena/prefs", {}, amy)
    check("S-03", "empty update -> 422", status == 422, status)
    status, body = call("GET", "/api/v1/arena/me", token=amy)
    check("S-04", "record carries settings", status == 200 and body["prefs"]["reduce_motion"] is True, body.get("prefs"))
    status, body = call("GET", "/api/v1/arena/prefs", token=ben)
    check("S-05", "settings are per player", status == 200 and body["reduce_motion"] is False, body)

    print("--- Leaderboard")
    status, board = call("GET", "/api/v1/arena/leaderboard?limit=100")
    row = next((p for p in board.get("players", []) if p["user_id"] == amy_id), None) if status == 200 else None
    check("L-01", "player with wins is listed", row and row["cases_won"] == 2 and row["wins"] == 3, row)
    check("L-02", "player with no wins is not listed", status == 200 and not any(p["user_id"] == ben_id for p in board["players"]))
    check("L-03", "no emails or account details", status == 200 and not any("email" in p or "role" in p for p in board["players"]))

    print("--- Reset")
    status, body = call("DELETE", "/api/v1/arena/results", token=amy)
    check("C-01", "clear my results", status == 200 and body["cleared"] == 4, body)
    status, body = call("GET", "/api/v1/arena/me", token=amy)
    check("C-02", "record is empty again", status == 200 and body["trials"] == 0, body)
    call("POST", "/api/v1/arena/results", result(), amy)  # keep one row for the admin checks

    print("--- Admin")
    status, _ = call("GET", "/api/v1/admin/arena", token=amy)
    check("A-01", "player cannot open the admin game overview -> 403", status == 403, status)
    admin_user, admin_pw = os.environ.get("TEST_ADMIN_USERNAME"), os.environ.get("TEST_ADMIN_PASSWORD")
    if admin_user and admin_pw:
        status, body = call("POST", "/api/v1/auth/login", {"username": admin_user, "password": admin_pw})
        admin = body.get("token") if status == 200 else None
        status, body = call("GET", "/api/v1/admin/arena", token=admin)
        ok = status == 200
        check("A-02", "admin overview has totals", ok and body["overview"]["trials"] >= 1, body.get("overview") if ok else body)
        case = next((c for c in body["cases"] if c["case_id"] == "bureaucratic-delay"), None) if ok else None
        check("A-03", "per-case stats", case and case["wins"] >= 1 and case["tier"] == 1, case)
        mine = next((p for p in body["players"] if p["id"] == amy_id), None) if ok else None
        check("A-04", "per-player activity", mine and mine["trials"] == 1 and mine["cases_won"] == 1, mine)
        check("A-05", "no emails or password hashes", ok and not any("email" in p or "password_hash" in p for p in body["players"]))
    else:
        print("  admin checks skipped: TEST_ADMIN_USERNAME / TEST_ADMIN_PASSWORD not set")

    print("--- CORS")
    origin = os.environ.get("TEST_ARENA_ORIGIN", "https://just-give-up-atp.vercel.app")
    req = urllib.request.Request(BASE + "/api/v1/arena/leaderboard", headers={"Origin": origin})
    with urllib.request.urlopen(req, timeout=30) as res:
        allowed = res.headers.get("access-control-allow-origin")
    check("X-01", f"API allows browser calls from {origin}", allowed == origin, allowed)

    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        print("--- Database rules (as lawliet_app)")
        import psycopg2
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', 'user', true)", (str(ben_id),))
                try:
                    cur.execute("INSERT INTO arena_results (user_id, case_id, tier, won, turns, jp_left) "
                                "VALUES (%s, 'missing-fact', 1, true, 2, 99)", (amy_id,))
                    check("D-01", "cannot save a result as someone else", False, "insert was allowed")
                except psycopg2.Error:
                    check("D-01", "cannot save a result as someone else", True)
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', 'user', true)", (str(ben_id),))
                cur.execute("DELETE FROM arena_results WHERE user_id = %s", (amy_id,))
                check("D-02", "cannot clear someone else's results", cur.rowcount == 0)
                cur.execute("SELECT COUNT(*) FROM arena_prefs WHERE user_id = %s", (amy_id,))
                check("D-03", "cannot read someone else's settings", cur.fetchone()[0] == 0)
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', 'user', true)", (str(amy_id),))
                try:
                    cur.execute("UPDATE arena_results SET won = true WHERE user_id = %s", (amy_id,))
                    check("D-04", "results cannot be edited", False, "update was allowed")
                except psycopg2.Error:
                    check("D-04", "results cannot be edited", True)
            conn.rollback()
        finally:
            conn.close()
finally:
    print("--- Clean up")
    for token, name in ((amy, f"g_a{RUN}"), (ben, f"g_b{RUN}")):
        status, _ = call("DELETE", "/api/v1/me", {"confirm": name, "password": PASSWORD}, token)
        print(f"  deleted {name}: {status}")

passed = sum(ok for _, ok in results)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

"""Phase 7.3 verification against a deployed L-Lawliet API.

    python scripts/verify_deploy.py https://l-lawliet-three.vercel.app

Logs in with the seed accounts from .env, creates the temporary law RA 99999,
updates and deletes it through the deployed API, and confirms each step with a
direct query in Neon (as lawliet_app). Prints one line per check. No secrets are
printed. The test law is always removed at the end, even if a check fails.
"""
import json
import os
import sys
import urllib.error
import urllib.request

import psycopg2
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://l-lawliet-three.vercel.app").rstrip("/")
TEST_RA = "RA 99999"
TEST_LAW = dict(
    ra_number=TEST_RA, official_title="TEST ONLY - Sample Act", plain_title="TEST ONLY law",
    category="Environment", year=2026, reading_time_minutes=3, importance_rating=2,
    tldr_summary="A temporary law used only for deployment testing.",
    full_breakdown="Created by scripts/verify_deploy.py and deleted at the end of the run.",
    why_it_matters="Testing only.", example_scenario="Used to verify create, update and delete.",
    penalties="None.", min_fine_php=1000, total_sections=1, enacting_president="Test President",
    target_audience="Testers", source_url="https://example.com/test-only",
)


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "lawliet-verify-deploy")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None)


db = psycopg2.connect(os.environ["DATABASE_URL"])
db.autocommit = True


def sql(q, p=()):
    with db.cursor() as cur:
        cur.execute(q, p)
        return cur.fetchall() if cur.description else []


results = []


def check(n, name, ok, detail):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {n:>2}  {name:32} {detail}")


print(f"Target: {BASE}\n")
s, admin = call("POST", "/api/v1/auth/login", {"username": os.environ["SEED_ADMIN_USERNAME"], "password": os.environ["SEED_ADMIN_PASSWORD"]})
s2, user = call("POST", "/api/v1/auth/login", {"username": os.environ["SEED_USER_USERNAME"], "password": os.environ["SEED_USER_PASSWORD"]})
if s != 200 or s2 != 200:
    sys.exit(f"Login failed (admin {s}, user {s2}); check the SEED_ accounts in .env")
A, U = admin["token"], user["token"]
sql("DELETE FROM laws WHERE ra_number = %s", (TEST_RA,))  # leftover from an earlier run

try:
    s, h = call("GET", "/api/health")
    check(1, "The API is reachable", s == 200, f"GET /api/health -> {s}")
    check(2, "It connects to the database", (h or {}).get("database") == "connected", f"database = {(h or {}).get('database')}")

    sg, g = call("GET", "/api/v1/laws")
    su, u = call("GET", "/api/v1/laws", token=U)
    check(3, "Existing records are returned", sg == su == 200 and g["count"] == 10 and u["count"] == u["total"],
          f"guest {g['count']} of {g['total']} ({g['access']}); user {u['count']} of {u['total']} ({u['access']})")

    s, law = call("POST", "/api/v1/laws", TEST_LAW, token=A)
    lid = (law or {}).get("id")
    check(4, "A record can be created", s == 201, f"POST /api/v1/laws -> {s}, id {lid}")
    row = sql("SELECT id, min_fine_php FROM laws WHERE ra_number = %s", (TEST_RA,))
    check(5, "It appears in the database", len(row) == 1 and row[0][0] == lid, f"Neon row: {row}")

    before = sql("SELECT updated_at FROM laws WHERE id = %s", (lid,))[0][0]
    s, _ = call("PATCH", f"/api/v1/laws/{lid}", {"min_fine_php": 5000}, token=A)
    check(6, "A record can be updated", s == 200, f"PATCH min_fine_php=5000 -> {s}")
    fine, after = sql("SELECT min_fine_php, updated_at FROM laws WHERE id = %s", (lid,))[0]
    check(7, "The change is in the database", fine == 5000 and after > before, f"Neon: min_fine_php {fine}, updated_at moved {after > before}")

    s, _ = call("DELETE", f"/api/v1/laws/{lid}", token=A)
    check(8, "A record can be deleted", s == 204, f"DELETE -> {s}")
    left = sql("SELECT COUNT(*) FROM laws WHERE id = %s", (lid,))[0][0]
    s404, _ = call("GET", f"/api/v1/laws/{lid}", token=U)
    check(9, "It is gone from the database", left == 0 and s404 == 404, f"Neon rows {left}; GET -> {s404}")

    note = sql("SELECT COUNT(*) FROM comments WHERE law_id = 1 AND user_name = 'Juan D.'")[0][0]
    check(10, "Seeded data still present", u["total"] >= 30 and note == 1,
          f"total {u['total']}, Juan D. note present: {note == 1} (run again after a redeploy for persistence)")
finally:
    sql("DELETE FROM laws WHERE ra_number = %s", (TEST_RA,))
    db.close()

print(f"\n{sum(results)}/{len(results)} passed. Test law removed.")

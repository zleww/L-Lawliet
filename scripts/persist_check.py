"""Phase 8 persistence tests P-02 and P-03 across a Vercel redeploy.

    python scripts/persist_check.py prepare https://l-lawliet-three.vercel.app
    (redeploy production on Vercel and wait until it is Ready)
    python scripts/persist_check.py check   https://l-lawliet-three.vercel.app

prepare: creates two TEST ONLY laws through the deployed API, updates the first
         (P-02) and deletes the second (P-03). Their ids are saved in a temp file.
check:   after the redeploy, reads both through the deployed API and in Neon,
         prints the results, then deletes the remaining test law.
No secrets are printed.
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

import psycopg2
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))
STEP = sys.argv[1] if len(sys.argv) > 1 else ""
BASE = (sys.argv[2] if len(sys.argv) > 2 else "https://l-lawliet-three.vercel.app").rstrip("/")
STATE = os.path.join(tempfile.gettempdir(), "lawliet_persist_check.json")
RA_UPDATED, RA_DELETED = "RA 99997", "RA 99998"


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "lawliet-persist-check")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None)


def law(ra, title):
    return dict(ra_number=ra, official_title=f"TEST ONLY - {title}", plain_title=f"TEST ONLY {title}",
                category="Environment", year=2026, reading_time_minutes=3, importance_rating=2,
                tldr_summary="A temporary law for the redeploy persistence test.",
                full_breakdown="Created by scripts/persist_check.py and removed by its check step.",
                why_it_matters="Testing only.", example_scenario="Used to check data survives a redeploy.",
                penalties="None.", min_fine_php=1000, total_sections=1, enacting_president="Test President",
                target_audience="Testers", source_url="https://example.com/test-only")


def login(prefix):
    s, j = call("POST", "/api/v1/auth/login", {"username": os.environ[f"SEED_{prefix}_USERNAME"],
                                               "password": os.environ[f"SEED_{prefix}_PASSWORD"]})
    if s != 200:
        sys.exit(f"{prefix.lower()} login failed ({s}); check .env")
    return j["token"]


db = psycopg2.connect(os.environ["DATABASE_URL"])
db.autocommit = True


def sql(q, p=()):
    with db.cursor() as cur:
        cur.execute(q, p)
        return cur.fetchall() if cur.description else []


admin = login("ADMIN")

if STEP == "prepare":
    sql("DELETE FROM laws WHERE ra_number IN (%s, %s)", (RA_UPDATED, RA_DELETED))
    s1, a = call("POST", "/api/v1/laws", law(RA_UPDATED, "updated before redeploy"), admin)
    s2, _ = call("PATCH", f"/api/v1/laws/{a['id']}", {"min_fine_php": 7777}, admin)
    s3, b = call("POST", "/api/v1/laws", law(RA_DELETED, "deleted before redeploy"), admin)
    s4, _ = call("DELETE", f"/api/v1/laws/{b['id']}", token=admin)
    json.dump({"updated": a["id"], "deleted": b["id"], "base": BASE}, open(STATE, "w"))
    print(f"P-02 prepare: POST {s1} (id {a['id']}), PATCH min_fine_php=7777 -> {s2}")
    print(f"P-03 prepare: POST {s3} (id {b['id']}), DELETE -> {s4}")
    print("\nNow redeploy production on Vercel, wait for Ready, then run:")
    print(f"  python scripts/persist_check.py check {BASE}")

elif STEP == "check":
    st = json.load(open(STATE))
    user = login("USER")
    s, a = call("GET", f"/api/v1/laws/{st['updated']}", token=user)
    row = sql("SELECT min_fine_php FROM laws WHERE id = %s", (st["updated"],))
    ok2 = s == 200 and a["min_fine_php"] == 7777 and row == [(7777,)]
    print(f"{'PASS' if ok2 else 'FAIL'}  P-02  updated law after redeploy: GET {s}, min_fine_php {a.get('min_fine_php') if a else None}; Neon {row}")
    s, _ = call("GET", f"/api/v1/laws/{st['deleted']}", token=user)
    row = sql("SELECT COUNT(*) FROM laws WHERE id = %s", (st["deleted"],))[0][0]
    ok3 = s == 404 and row == 0
    print(f"{'PASS' if ok3 else 'FAIL'}  P-03  deleted law after redeploy: GET {s}; Neon rows {row}")
    s, _ = call("DELETE", f"/api/v1/laws/{st['updated']}", token=admin)
    sql("DELETE FROM laws WHERE ra_number IN (%s, %s)", (RA_UPDATED, RA_DELETED))
    os.remove(STATE)
    print(f"\nCleanup: DELETE -> {s}; laws now {sql('SELECT COUNT(*) FROM laws')[0][0]}")

else:
    sys.exit("usage: python scripts/persist_check.py prepare|check [base-url]")

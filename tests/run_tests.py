"""Phase 8 test run: functional, validation, security and integration tests.

    pip install -r requirements-dev.txt
    python tests/run_tests.py

Runs the API in-process (FastAPI TestClient) against the real Neon database
from .env, logs in with the seeded accounts, and confirms every data change
with its own SQL query as lawliet_app. Prints one PASS/FAIL line per test ID
from the Phase 8 tables. The temporary law RA 99999 and every test comment
are deleted at the end, even if a test fails. No secrets are printed.

Not covered here (they need a restart, a redeploy or a browser):
P-01 to P-04 (scripts/persist_check.py and a local restart), I-05 and I-06.
"""
import logging
import os
import sys
import warnings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
os.chdir(ROOT)

import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))
logging.disable(logging.CRITICAL)
from fastapi.testclient import TestClient

import index
from _auth import create_token

c = TestClient(index.app, raise_server_exceptions=False)
db = psycopg2.connect(os.environ["DATABASE_URL"])
db.autocommit = True
TEST_RA = "RA 99999"
results = []


def sql(q, p=()):
    with db.cursor() as cur:
        cur.execute(q, p)
        return cur.fetchall() if cur.description else []


def nrows():
    return sql("SELECT COUNT(*) FROM laws WHERE has_guide")[0][0]


def check(tid, desc, ok, actual):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {tid:5}  {desc:52} {actual}")


def login(u, p):
    return c.post("/api/v1/auth/login", json={"username": u, "password": p})


LAW = dict(
    ra_number=TEST_RA, official_title="TEST ONLY - Sample Act", plain_title="TEST ONLY law",
    category="Environment", year=2026, reading_time_minutes=3, importance_rating=2,
    tldr_summary="A temporary law used only for testing.",
    full_breakdown="Created by tests/run_tests.py and deleted at the end of the run.",
    why_it_matters="Testing only.", example_scenario="Used to verify create, update and delete.",
    penalties="None.", min_fine_php=1000, total_sections=1, enacting_president="Test President",
    target_audience="Testers", source_url="https://example.com/test-only",
)

ADMIN, USER = os.environ["SEED_ADMIN_USERNAME"], os.environ["SEED_USER_USERNAME"]
ra, ru = login(ADMIN, os.environ["SEED_ADMIN_PASSWORD"]), login(USER, os.environ["SEED_USER_PASSWORD"])
if ra.status_code != 200 or ru.status_code != 200:
    sys.exit(f"Login failed (admin {ra.status_code}, user {ru.status_code}); check the SEED_ accounts in .env")
A = {"Authorization": "Bearer " + ra.json()["token"]}
U = {"Authorization": "Bearer " + ru.json()["token"]}
sql("DELETE FROM laws WHERE ra_number = %s", (TEST_RA,))  # leftover from an earlier run
start_laws, start_comments = nrows(), sql("SELECT COUNT(*) FROM comments")[0][0]
print(f"L-Lawliet Phase 8 tests against Neon. Starting with {start_laws} laws and {start_comments} comments.\n")

try:
    print("A. Functional")
    r = c.post("/api/v1/laws", json=LAW, headers=A)
    nid = r.json().get("id")
    row = sql("SELECT ra_number, min_fine_php, category FROM laws WHERE ra_number = %s", (TEST_RA,))
    check("F-01", "Create a law as admin; row in Neon", r.status_code == 201 and len(row) == 1, f"{r.status_code}, id {nid}; Neon {row}")
    r = c.get("/api/v1/laws", headers=U); j = r.json(); total = nrows()
    check("F-02", "List as user: full, count = total = table", r.status_code == 200 and j["access"] == "full" and j["count"] == j["total"] == total,
          f"{r.status_code}, {j['access']}, {j['count']} of {j['total']}; Neon {total}")
    r = c.get("/api/v1/laws"); j = r.json(); ids = [l["id"] for l in j["laws"]]
    check("F-03", "List as guest: first 10 only", r.status_code == 200 and j["access"] == "guest" and ids == sorted(ids)[:10] and len(ids) == 10,
          f"{r.status_code}, {j['access']}, {j['count']} of {j['total']}, ids {ids[0]}..{ids[-1]}")
    r = c.get("/api/v1/laws/1", headers=U); notes = [n["user_name"] for n in r.json().get("user_notes", [])]
    check("F-04", "Get law 1 with its comments (a list of named notes)",
          r.status_code == 200 and isinstance(r.json().get("user_notes"), list) and all(notes), f"{r.status_code}, notes {notes}")
    before = sql("SELECT ra_number, official_title, year, min_fine_php, updated_at FROM laws WHERE id = %s", (nid,))[0]
    r = c.patch(f"/api/v1/laws/{nid}", json={"min_fine_php": 5000}, headers=A)
    after = sql("SELECT ra_number, official_title, year, min_fine_php, updated_at FROM laws WHERE id = %s", (nid,))[0]
    check("F-05", "Update one field only", r.status_code == 200 and after[3] == 5000 and after[:3] == before[:3] and after[4] > before[4],
          f"{r.status_code}, fine {before[3]} -> {after[3]}, other columns unchanged, updated_at moved")
    r = c.get("/api/v1/laws/search?q=10175", headers=U); res = [l["ra_number"] for l in r.json()["results"]]
    check("F-07", "Search q=10175", r.status_code == 200 and "RA 10175" in res, f"{r.status_code}, {res}")
    r = c.get("/api/v1/laws?category=Environment", headers=U); env = r.json()["laws"]
    neon_env = sql("SELECT COUNT(*) FROM laws WHERE category = 'Environment'")[0][0]
    check("F-08", "Filter category=Environment", r.status_code == 200 and all(l["category"] == "Environment" for l in env) and len(env) == neon_env,
          f"{r.status_code}, API {len(env)}, Neon {neon_env}")

    print("\nB. Validation")
    n0 = nrows()
    cases = [("V-01", "Missing ra_number", {k: v for k, v in LAW.items() if k != "ra_number"}),
             ("V-02", "Wrong type: year 'abc'", {**LAW, "ra_number": "RA 99998", "year": "abc"}),
             ("V-03", "Out of range: importance_rating 9", {**LAW, "ra_number": "RA 99998", "importance_rating": 9}),
             ("V-04", "Not allowed: category 'Sports'", {**LAW, "ra_number": "RA 99998", "category": "Sports"})]
    for tid, desc, body in cases:
        r = c.post("/api/v1/laws", json=body, headers=A)
        check(tid, desc + " -> 422, no row", r.status_code == 422 and nrows() == n0, f"{r.status_code}, field {r.json()['detail'][0]['loc'][-1]}")
    r = c.patch(f"/api/v1/laws/{nid}", json={}, headers=A)
    check("V-05", "Empty update body -> 422", r.status_code == 422, f"{r.status_code}, {r.json()['detail'][0]['msg']}")
    r = c.post("/api/v1/laws", content=b'{"ra_number": "RA 1"', headers={**A, "Content-Type": "application/json"})
    check("V-06", "Malformed JSON -> 422, no stack trace", r.status_code == 422 and "Traceback" not in r.text, f"{r.status_code}, {r.json()['detail'][0]['type']}")
    r = c.post("/api/v1/laws", json=LAW, headers=A)
    check("V-07", "Duplicate RA number -> 409", r.status_code == 409 and nrows() == n0, f"{r.status_code}, {r.json()['detail']}")
    r = c.get("/api/v1/laws/99999999", headers=U)
    check("V-08", "Law 99999999 -> 404", r.status_code == 404, f"{r.status_code}, {r.json()['detail']}")
    r = c.get("/api/v1/laws/abc")
    check("V-09", "ID 'abc' -> 422", r.status_code == 422, f"{r.status_code}, {r.json()['detail'][0]['type']}")
    c0 = sql("SELECT COUNT(*) FROM comments")[0][0]
    r = c.post("/api/v1/laws/99999999/comments", json={"user_name": "x", "comment": "y"}, headers=U)
    check("V-10", "Comment on missing law -> 404, no row", r.status_code == 404 and sql("SELECT COUNT(*) FROM comments")[0][0] == c0,
          f"{r.status_code}, {r.json()['detail']}")

    print("\nC. Security")
    r = c.post("/api/v1/laws", json=LAW)
    check("S-01", "Create without a token -> 401", r.status_code == 401 and nrows() == n0, f"{r.status_code}, {r.json()['detail']}")
    r = c.delete(f"/api/v1/laws/{nid}", headers={"Authorization": A["Authorization"][:-4] + "abcd"})
    kept = sql("SELECT COUNT(*) FROM laws WHERE id = %s", (nid,))[0][0]
    check("S-02", "Tampered token delete -> 401, law kept", r.status_code == 401 and kept == 1, f"{r.status_code}, {r.json()['detail']}")
    os.environ["JWT_EXPIRE_MINUTES"] = "-1"
    expired = {"Authorization": "Bearer " + create_token({"id": 0, "username": USER, "role": "user"})}
    os.environ.pop("JWT_EXPIRE_MINUTES")
    r = c.get("/api/v1/laws", headers=expired)
    check("S-03", "Expired token -> 401 (API part)", r.status_code == 401, f"{r.status_code}, {r.json()['detail']}")
    codes = [c.post("/api/v1/laws", json={**LAW, "ra_number": "RA 99997"}, headers=U).status_code,
             c.patch(f"/api/v1/laws/{nid}", json={"year": 2000}, headers=U).status_code,
             c.delete(f"/api/v1/laws/{nid}", headers=U).status_code]
    check("S-04", "User POST/PATCH/DELETE -> 403 each", codes == [403, 403, 403] and nrows() == n0, f"{codes}, table unchanged")
    w1 = login(ADMIN, "wrong-password-123")
    check("S-05", "Wrong password -> 401", w1.status_code == 401, f"{w1.status_code}, {w1.json()['detail']}")
    w2 = login("no_such_user_xyz", "whatever123")
    check("S-06", "Unknown username -> same 401 as S-05", w2.status_code == 401 and w1.json() == w2.json(), f"{w2.status_code}, {w2.json()['detail']}")
    r = c.get("/api/v1/laws/25")
    check("S-07", "Guest asks for law 25 -> 401", r.status_code == 401, f"{r.status_code}, {r.json()['detail']}")
    g = [l["id"] for l in c.get("/api/v1/laws/search?q=8353").json()["results"]]
    f = [l["id"] for l in c.get("/api/v1/laws/search?q=8353", headers=U).json()["results"]]
    check("S-08", "Guest search stays in first 10", g == [] and f != [], f"guest {g}, user {f}")
    texts = ra.text + c.get("/api/v1/laws", headers=U).text + c.get("/api/v1/laws/99999999", headers=U).text
    check("S-09", "No secrets in responses", not any(s in texts for s in ("password_hash", "$2b$", "neon.tech", "Traceback")),
          "no hash, host, SQL or stack trace")

    print("\nE. Integration")
    r = c.get(f"/api/v1/laws/{nid}", headers=U)
    keys = ["ra_number", "official_title", "category", "year", "total_sections", "source_url"]
    row = dict(zip(keys, sql("SELECT " + ", ".join(keys) + " FROM laws WHERE id = %s", (nid,))[0]))
    check("I-01", "Create then read back: API = Neon", r.status_code == 200 and all(r.json()[k] == row[k] == LAW[k] for k in keys),
          f"{r.status_code}, {len(keys)} fields match")
    r = c.post(f"/api/v1/laws/{nid}/comments", json={"user_name": "Test Student", "comment": "TEST ONLY note"}, headers=U)
    crow = sql("SELECT c.law_id, u.username FROM comments c LEFT JOIN users u ON u.id = c.user_id WHERE c.comment = 'TEST ONLY note'")
    check("I-02", "Comment linked to law and token's user", r.status_code == 201 and crow == [(nid, USER)], f"{r.status_code}, Neon {crow}")
    had = sql("SELECT COUNT(*) FROM comments WHERE law_id = %s", (nid,))[0][0]
    r = c.delete(f"/api/v1/laws/{nid}", headers=A)
    left = sql("SELECT COUNT(*) FROM laws WHERE id = %s", (nid,))[0][0]
    left_c = sql("SELECT COUNT(*) FROM comments WHERE law_id = %s", (nid,))[0][0]
    g404 = c.get(f"/api/v1/laws/{nid}", headers=U).status_code
    check("F-06", "Delete the law -> 204, row gone, GET 404", r.status_code == 204 and left == 0 and g404 == 404, f"{r.status_code}, rows {left}, GET {g404}")
    check("I-03", "Delete cascades to its comments", had == 1 and left_c == 0, f"comments before {had}, after {left_c}")
    real = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = "postgresql://lawliet_app:wrong@127.0.0.1:1/neondb?connect_timeout=3"
    r = c.get("/api/v1/laws")
    os.environ["DATABASE_URL"] = real
    check("I-04", "Database unreachable -> 503, nothing leaked", r.status_code == 503 and "127.0.0.1" not in r.text and "lawliet_app" not in r.text,
          f"{r.status_code}, {r.json()['detail']}")
finally:
    sql("DELETE FROM laws WHERE ra_number = %s", (TEST_RA,))
    sql("DELETE FROM comments WHERE comment LIKE 'TEST ONLY%%'")
    end_laws, end_comments = nrows(), sql("SELECT COUNT(*) FROM comments")[0][0]
    db.close()

print(f"\n{sum(results)}/{len(results)} passed. Cleanup: {end_laws} laws, {end_comments} comments "
      f"(started with {start_laws} and {start_comments}).")
sys.exit(0 if all(results) else 1)

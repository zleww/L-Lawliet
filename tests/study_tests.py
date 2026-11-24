"""Tests for the JurisCard study endpoints (/api/v1/study/*) and the admin overview.

    python tests/study_tests.py                      # against http://127.0.0.1:8000
    python tests/study_tests.py https://<site>       # against a deployment

Creates two throwaway accounts (prefix s_), and deletes them at the end, which also
deletes their cards, marks, quiz scores and settings (ON DELETE CASCADE).
Reads from .env / the environment:
    DATABASE_URL        lawliet_app connection, for the database-level RLS checks
    TEST_ADMIN_USERNAME / TEST_ADMIN_PASSWORD   optional; enables the admin checks
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
    status, body = call("POST", "/api/v1/auth/register", {"username": username, "password": PASSWORD, "email": f"{username}@example.test"})
    if status != 201:
        sys.exit(f"could not create {username}: {status} {body}")
    return body["token"], body["user"]["id"]


print(f"Testing {BASE}  (run {RUN})")
alice, alice_id = register(f"s_a{RUN}")
bob, bob_id = register(f"s_b{RUN}")
law_id = call("GET", "/api/v1/laws")[1]["laws"][0]["id"]

try:
    print("--- Guests")
    for path in ("/api/v1/study/summary", "/api/v1/study/cards", "/api/v1/study/progress",
                 "/api/v1/study/quizzes", "/api/v1/study/prefs"):
        status, _ = call("GET", path)
        check("G-01", f"guest GET {path} -> 401", status == 401, status)
    status, _ = call("PUT", f"/api/v1/study/progress/{law_id}", {"status": "mastered"})
    check("G-02", "guest cannot save a mark", status == 401, status)
    status, _ = call("POST", "/api/v1/study/quizzes", {"score": 3, "total": 5})
    check("G-03", "guest cannot save a quiz score", status == 401, status)

    print("--- Own cards")
    status, card = call("POST", "/api/v1/study/cards", {
        "category": "Technology & Crime", "question": "What is RA 10175 about?",
        "answer": "Cybercrime.", "source": "RA 10175"}, alice)
    check("C-01", "create a card -> 201", status == 201 and card["status"] == "new", status)
    card_id = card["id"] if status == 201 else 0
    status, body = call("GET", "/api/v1/study/cards", token=alice)
    check("C-02", "list shows the card", status == 200 and body["count"] == 1, body)
    status, body = call("PATCH", f"/api/v1/study/cards/{card_id}", {"status": "mastered", "answer": "Cybercrime law."}, alice)
    check("C-03", "edit own card", status == 200 and body["status"] == "mastered" and body["answer"] == "Cybercrime law.", body)
    status, body = call("GET", "/api/v1/study/cards", token=bob)
    check("C-04", "another user does not see it", status == 200 and body["count"] == 0, body)
    status, _ = call("PATCH", f"/api/v1/study/cards/{card_id}", {"status": "review"}, bob)
    check("C-05", "another user cannot edit it -> 404", status == 404, status)
    status, _ = call("DELETE", f"/api/v1/study/cards/{card_id}", token=bob)
    check("C-06", "another user cannot delete it -> 404", status == 404, status)
    status, _ = call("POST", "/api/v1/study/cards", {"category": "Cooking", "question": "abcde", "answer": "ab"}, alice)
    check("C-07", "unknown category -> 422", status == 422, status)
    status, _ = call("POST", "/api/v1/study/cards", {"category": "Environment", "question": "abc", "answer": "ab"}, alice)
    check("C-08", "question too short -> 422", status == 422, status)
    status, _ = call("PATCH", f"/api/v1/study/cards/{card_id}", {}, alice)
    check("C-09", "empty update -> 422", status == 422, status)
    status, _ = call("POST", "/api/v1/study/cards", {"category": "Environment", "question": "abcde",
                                                     "answer": "ab", "user_id": bob_id}, alice)
    check("C-10", "extra field (user_id) rejected -> 422", status == 422, status)

    print("--- Law marks")
    status, body = call("PUT", f"/api/v1/study/progress/{law_id}", {"status": "review"}, alice)
    check("P-01", "mark a law for review", status == 200 and body["status"] == "review", body)
    status, body = call("PUT", f"/api/v1/study/progress/{law_id}", {"status": "mastered"}, alice)
    check("P-02", "change the mark (upsert)", status == 200, body)
    status, body = call("GET", "/api/v1/study/progress", token=alice)
    marks = body["progress"] if status == 200 else []
    check("P-03", "one mark saved, as mastered", len(marks) == 1 and marks[0]["status"] == "mastered", body)
    status, body = call("GET", "/api/v1/study/progress", token=bob)
    check("P-04", "another user sees no marks", status == 200 and body["progress"] == [], body)
    status, _ = call("PUT", "/api/v1/study/progress/999999", {"status": "review"}, alice)
    check("P-05", "unknown law -> 404", status == 404, status)
    status, _ = call("PUT", f"/api/v1/study/progress/{law_id}", {"status": "done"}, alice)
    check("P-06", "bad status -> 422", status == 422, status)

    print("--- Quizzes")
    status, body = call("POST", "/api/v1/study/quizzes", {"score": 7, "total": 10, "category": "Environment"}, alice)
    check("Q-01", "save a score -> 201", status == 201 and body["score"] == 7, body)
    status, _ = call("POST", "/api/v1/study/quizzes", {"score": 11, "total": 10}, alice)
    check("Q-02", "score above total -> 422", status == 422, status)
    status, _ = call("POST", "/api/v1/study/quizzes", {"score": 1, "total": 0}, alice)
    check("Q-03", "zero questions -> 422", status == 422, status)
    status, body = call("GET", "/api/v1/study/quizzes", token=alice)
    check("Q-04", "history has one attempt", status == 200 and len(body["attempts"]) == 1, body)

    print("--- Settings")
    status, body = call("GET", "/api/v1/study/prefs", token=alice)
    check("S-01", "defaults before saving", status == 200 and body == {"quiz_length": 10, "daily_goal": 10, "hide_mastered": False}, body)
    status, body = call("PATCH", "/api/v1/study/prefs", {"quiz_length": 15, "hide_mastered": True}, alice)
    check("S-02", "save settings", status == 200 and body["quiz_length"] == 15 and body["hide_mastered"] is True, body)
    status, body = call("PATCH", "/api/v1/study/prefs", {"daily_goal": 25}, alice)
    check("S-03", "partial update keeps the rest", status == 200 and body["quiz_length"] == 15 and body["daily_goal"] == 25, body)
    status, _ = call("PATCH", "/api/v1/study/prefs", {"quiz_length": 7}, alice)
    check("S-04", "quiz length outside 5/10/15/20 -> 422", status == 422, status)
    status, _ = call("PATCH", "/api/v1/study/prefs", {"daily_goal": 0}, alice)
    check("S-05", "daily goal 0 -> 422", status == 422, status)

    print("--- Summary")
    status, s = call("GET", "/api/v1/study/summary", token=alice)
    ok = status == 200
    mastered = sum(c["laws_mastered"] + c["cards_mastered"] for c in s["categories"]) if ok else -1
    check("U-01", "summary counts 1 law + 1 card mastered", ok and mastered == 2, s)
    check("U-02", "marked today counts both", ok and s["marked_today"] == 2, s.get("marked_today") if ok else s)
    check("U-03", "quiz stats", ok and s["quizzes"]["attempts"] == 1 and s["quizzes"]["average_pct"] == 70, s.get("quizzes") if ok else s)
    check("U-04", "recent activity lists 3 items", ok and len(s["recent"]) == 3, s.get("recent") if ok else s)
    check("U-05", "summary carries saved settings", ok and s["prefs"]["daily_goal"] == 25, s.get("prefs") if ok else s)

    print("--- Reset")
    status, body = call("DELETE", "/api/v1/study/progress", token=alice)
    check("R-01", "reset clears the law mark and the card status", status == 200 and body["cleared"] == 2, body)
    status, body = call("GET", "/api/v1/study/cards", token=alice)
    check("R-02", "card is kept, back to new", status == 200 and body["count"] == 1 and body["cards"][0]["status"] == "new", body)

    print("--- Admin")
    status, _ = call("GET", "/api/v1/admin/overview", token=alice)
    check("A-01", "user cannot open the admin overview -> 403", status == 403, status)
    status, _ = call("GET", "/api/v1/admin/study-activity")
    check("A-02", "guest cannot list study activity -> 401", status == 401, status)
    admin_user, admin_pw = os.environ.get("TEST_ADMIN_USERNAME"), os.environ.get("TEST_ADMIN_PASSWORD")
    if admin_user and admin_pw:
        status, body = call("POST", "/api/v1/auth/login", {"username": admin_user, "password": admin_pw})
        admin = body.get("token") if status == 200 else None
        status, body = call("GET", "/api/v1/admin/overview", token=admin)
        check("A-03", "admin overview", status == 200 and body["users"] >= 2 and body["quiz_attempts"] >= 1, body)
        status, body = call("GET", "/api/v1/admin/study-activity", token=admin)
        mine = [u for u in body.get("users", []) if u["id"] == alice_id] if status == 200 else []
        check("A-04", "admin sees per-account activity", mine and mine[0]["quizzes"] == 1 and mine[0]["flashcards"] == 1, mine)
        check("A-05", "no password hashes or emails in the list",
              status == 200 and not any("password_hash" in u or "email" in u for u in body["users"]))
    else:
        print("  admin checks skipped: TEST_ADMIN_USERNAME / TEST_ADMIN_PASSWORD not set")

    print("--- CORS")
    origin = os.environ.get("TEST_JURISCARD_ORIGIN", "https://juris-card.vercel.app")
    req = urllib.request.Request(BASE + "/api/v1/stats", headers={"Origin": origin})
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
                cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', 'user', true)", (str(bob_id),))
                cur.execute("SELECT COUNT(*) FROM flashcards WHERE user_id = %s", (alice_id,))
                check("D-01", "RLS hides another user's cards", cur.fetchone()[0] == 0)
                cur.execute("UPDATE flashcards SET answer = 'x' WHERE user_id = %s", (alice_id,))
                check("D-02", "RLS blocks editing another user's cards", cur.rowcount == 0)
                try:
                    cur.execute("INSERT INTO quiz_attempts (user_id, score, total) VALUES (%s, 1, 1)", (alice_id,))
                    check("D-03", "cannot save a score as someone else", False, "insert was allowed")
                except psycopg2.Error:
                    check("D-03", "cannot save a score as someone else", True)
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_id', %s, true), set_config('app.role', 'user', true)", (str(alice_id),))
                try:
                    cur.execute("UPDATE quiz_attempts SET score = 10 WHERE user_id = %s", (alice_id,))
                    check("D-04", "quiz scores cannot be edited", False, "update was allowed")
                except psycopg2.Error:
                    check("D-04", "quiz scores cannot be edited", True)
            conn.rollback()
        finally:
            conn.close()
finally:
    print("--- Clean up")
    for token, name in ((alice, f"s_a{RUN}"), (bob, f"s_b{RUN}")):
        status, _ = call("DELETE", "/api/v1/me", {"confirm": name, "password": PASSWORD}, token)
        print(f"  deleted {name}: {status}")

passed = sum(ok for _, ok in results)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

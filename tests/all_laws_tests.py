"""Tests for migration 010: laws without a guide can be opened, saved, rated and noted,
while every guide list stays guides only.

    python tests/all_laws_tests.py                      # against http://127.0.0.1:8000
    python tests/all_laws_tests.py https://<site>       # against a deployment

Creates one throwaway account (prefix t_), and removes its note, rating, save and the
account itself at the end.
"""
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
RUN = secrets.token_hex(3)
results = []


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=40) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            return err.code, json.loads(raw) if raw else None
        except ValueError:
            return err.code, raw.decode(errors="replace")


def check(test_id, name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {test_id}  {name}" + ("" if ok else f"  -> {detail}"))


print(f"Testing {BASE}  (run {RUN})")

# A law with no guide: BP 22 (Bouncing Checks Law)
s, b = call("GET", "/api/v1/law-index?" + urllib.parse.urlencode({"q": "BP 22"}))
row = b["items"][0] if s == 200 and b["items"] else {}
law_id = row.get("law_id")
check("AL-01", "BP 22 in the full list is linked to a law row and has no guide",
      bool(law_id) and row.get("has_guide") is False, f"{s} {row}")

s, b = call("GET", f"/api/v1/laws/{law_id}")
check("AL-02", "a guest can open a law that has no guide",
      s == 200 and b["has_guide"] is False and b["label"] == "Batas Pambansa Blg. 22" and b["plain_title"] is None,
      f"{s} {b if s != 200 else ''}")

s, b = call("GET", "/api/v1/laws")
check("AL-03", "guest guide list is still the first 10 guides of the guides only",
      s == 200 and b["count"] == 10 and b["total"] < 1000 and all(l["has_guide"] for l in b["laws"]), f"{s} {b.get('total')}")

s, b = call("GET", "/api/v1/stats")
check("AL-04", "stats count guides only, by their 6 categories",
      s == 200 and b["total"] < 1000 and None not in b["categories"] and "null" not in b["categories"], f"{s} {b}")

username = f"t_all_{RUN}"
password = f"Passw0rd{RUN}"
s, b = call("POST", "/api/v1/auth/register",
            {"username": username, "password": password, "email": f"{username}@example.test"})
token = b.get("token") if s == 201 and isinstance(b, dict) else None
check("AL-05", "throwaway account registers and logs in", bool(token), f"{s} {b}")

note_id = None
try:
    s, b = call("GET", "/api/v1/laws?" + urllib.parse.urlencode({"search": "Bouncing"}), token=token)
    check("AL-06", "logged-in guide search does not return laws without a guide",
          s == 200 and all(l["has_guide"] for l in b["laws"]), f"{s}")

    s, _ = call("POST", f"/api/v1/laws/{law_id}/save", token=token)
    s2, saved = call("GET", "/api/v1/me/saved", token=token)
    mine = [l for l in (saved or {}).get("saved", []) if l["id"] == law_id]
    check("AL-07", "save a law with no guide; it shows in saved laws with a title and category",
          s == 201 and mine and mine[0]["plain_title"] and mine[0]["category"] == "Full list", f"{s} {s2} {mine}")

    s, _ = call("PUT", f"/api/v1/laws/{law_id}/rating", {"rating": 4}, token=token)
    s2, b = call("GET", f"/api/v1/laws/{law_id}", token=token)
    check("AL-08", "rate it 4 stars; the law shows my rating", s == 200 and b.get("my_rating") == 4, f"{s} {s2}")

    s, b = call("POST", f"/api/v1/laws/{law_id}/comments",
                {"user_name": username, "comment": "Test note on a listed law, removed by the test."}, token=token)
    note_id = next((n["id"] for n in (b or {}).get("comments", []) if n["user_name"] == username), None) if s == 201 else None
    s2, b2 = call("GET", f"/api/v1/law-index?" + urllib.parse.urlencode({"q": "BP 22"}))
    item = b2["items"][0] if s2 == 200 else {}
    check("AL-09", "add a note; the full-list card counts it and the rating",
          bool(note_id) and item.get("note_count", 0) >= 1 and item.get("rating_count", 0) >= 1, f"{s} {b} {item}")

finally:
    if token:
        if note_id:
            call("DELETE", f"/api/v1/comments/{note_id}", token=token)
        call("DELETE", f"/api/v1/laws/{law_id}/rating", token=token)
        call("DELETE", f"/api/v1/laws/{law_id}/save", token=token)
        s, _ = call("DELETE", "/api/v1/me", {"confirm": username, "password": password}, token=token)
        print(f"--- Cleanup: note, rating and save removed; account deleted: {'yes' if s == 204 else s}")

passed = sum(results)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

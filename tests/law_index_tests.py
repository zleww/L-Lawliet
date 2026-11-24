"""Tests for the full list of statutes (migration 009, GET /api/v1/law-index). Read only.

    python tests/law_index_tests.py                      # against http://127.0.0.1:8000
    python tests/law_index_tests.py https://<site>       # against a deployment
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
results = []


def get(path, **params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"null")


def check(test_id, name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {test_id}  {name}" + ("" if ok else f"  -> {detail}"))


print(f"Testing {BASE}")

s, b = get("/api/v1/law-index")
check("LI-01", "guest gets page 1 of the full list, 25 rows, newest year first",
      s == 200 and len(b["items"]) == 25 and b["total"] > 15000
      and b["items"][0]["year"] >= b["items"][-1]["year"], f"{s} {b and b.get('total')}")

s, b = get("/api/v1/law-index", q="RA 10175")
check("LI-02", "'RA 10175' finds exactly the Cybercrime law, linked to its guide",
      s == 200 and b["total"] == 1 and b["items"][0]["law_type"] == "ra" and b["items"][0]["law_id"],
      f"{s} {b}")

s, b = get("/api/v1/law-index", q="Republic Act No. 9262")
check("LI-03", "'Republic Act No. 9262' finds RA 9262", s == 200 and b["total"] == 1
      and b["items"][0]["number"] == "9262", f"{s} {b}")

s, b = get("/api/v1/law-index", q="BP 22")
check("LI-04", "'BP 22' finds the Bouncing Checks Law",
      s == 200 and b["total"] == 1 and "check" in b["items"][0]["official_title"].lower(), f"{s} {b}")

s, b = get("/api/v1/law-index", q="data privacy")
check("LI-05", "word search 'data privacy' ranks RA 10173 in the first page",
      s == 200 and any(i["number"] == "10173" for i in b["items"]), f"{s} {b and b.get('total')}")

s, b = get("/api/v1/law-index", type="pd", per_page=50)
check("LI-06", "type=pd returns only Presidential Decrees",
      s == 200 and b["total"] > 1000 and all(i["law_type"] == "pd" for i in b["items"]), f"{s}")

s, b = get("/api/v1/law-index", year=1987, type="ra")
check("LI-07", "year=1987 returns only laws dated 1987",
      s == 200 and all(i["year"] == 1987 for i in b["items"]), f"{s}")

s, b = get("/api/v1/law-index", per_page=51)
check("LI-08", "per_page above 50 -> 422", s == 422, f"{s}")

s, b = get("/api/v1/law-index", type="eo")
check("LI-09", "unknown type -> 422", s == 422, f"{s}")

s, b = get("/api/v1/law-index", q="'; DROP TABLE laws; --")
check("LI-10", "SQL-looking search text is just text -> 200", s == 200, f"{s} {b}")

s, b = get("/api/v1/law-index", q="zzqxjv nonexistent")
check("LI-11", "no match -> 200 with total 0", s == 200 and b["total"] == 0 and b["items"] == [], f"{s} {b}")

s, b = get("/api/v1/stats")
check("LI-12", "stats include the listed count", s == 200 and b.get("listed", 0) > 15000, f"{s} {b}")

passed = sum(results)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)

"""Build scripts/law_index.csv: every Philippine statute's number, date and official title.

Source: the public year pages of the LawPhil Project (lawphil.net), one page per law type per year.
Pages are cached so a rerun only downloads what is missing, and requests are spaced out.

    python scripts/fetch_law_index.py <cache-dir>
"""

import csv
import html
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "https://lawphil.net/statutes"
OUT = Path(__file__).with_name("law_index.csv")
CURRENT_YEAR = datetime.now().year

# code, folder, page prefix, label, first year, last year
TYPES = [
    ("act", "acts", "act", "Act", 1900, 1935),
    ("ca", "comacts", "ca", "Commonwealth Act", 1935, 1946),
    ("ra", "repacts", "ra", "Republic Act", 1946, CURRENT_YEAR),
    ("pd", "presdecs", "pd", "Presidential Decree", 1972, 1986),
    ("bp", "bataspam", "bp", "Batas Pambansa", 1978, 1986),
]

# One table row: number/date cell, title cell, then an optional PDF cell. A law whose HTML
# page is not up yet is linked with `xref` instead of `href`; then the PDF is the link.
ROW = re.compile(
    r'<a (?:class="[^"]*"\s+)?(?P<attr>href|xref)="(?P<file>(?P<code>[a-z]+)_(?P<num>[0-9]+[A-Za-z-]*)'
    r'_(?P<year>\d{4})\.html)">[^<]*</a>'
    r"\s*<br\s*/?>\s*(?P<date>[^<]*?)\s*</td>\s*<td[^>]*>(?P<title>.*?)</td>"
    r'(?:\s*<td[^>]*>\s*<a href="(?P<pdf>[^"]+\.pdf)")?',
    re.S | re.I,
)
TAG = re.compile(r"<[^>]+>")


def fetch(url: str, cache: Path) -> str | None:
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (law index builder)"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            text = resp.read().decode("cp1252", errors="replace")
    except urllib.error.HTTPError as err:
        if err.code == 404:
            text = ""
        else:
            raise
    finally:
        time.sleep(1.5)
    cache.write_text(text, encoding="utf-8")
    return text


def clean(value: str) -> str:
    return " ".join(html.unescape(TAG.sub(" ", value)).split())


MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
TYPOS = {"arpil": "april", "februaty": "february", "febuary": "february", "agust": "august"}
DATE = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2})\s*[.,]*\s*(\d{4})")


def parse_date(value: str) -> str:
    """'June 17. 1961', 'May 22 2007', 'August 8, 2004 (lapsed)' -> ISO date; '' if unreadable."""
    m = DATE.search(value)
    if not m:
        return ""
    word = TYPOS.get(m[1].lower(), m[1].lower())
    month = MONTHS.get(word) or next((n for name, n in MONTHS.items() if name.startswith(word[:3])), None)
    try:
        return datetime(int(m[3]), month, int(m[2])).date().isoformat() if month else ""
    except ValueError:
        return ""


def main() -> None:
    cache_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".law-cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows: dict[tuple[str, str], dict] = {}
    for code, folder, prefix, label, first, last in TYPES:
        before = len(rows)
        for year in range(first, last + 1):
            url = f"{BASE}/{folder}/{prefix}{year}/{prefix}{year}.html"
            page = fetch(url, cache_dir / f"{prefix}{year}.html")
            for m in ROW.finditer(page or ""):
                if m["code"].lower() != prefix:
                    continue
                key = (code, m["num"])
                if key in rows:
                    continue
                title = clean(m["title"])
                if not title:
                    continue
                rows[key] = {
                    "law_type": code,
                    "number": m["num"],
                    "label": f"{label} No. {m['num']}" if code != "bp" else f"Batas Pambansa Blg. {m['num']}",
                    "enacted_on": parse_date(clean(m["date"])),
                    "year": int(m["year"]),
                    "official_title": title,
                    "source_url": f"{BASE}/{folder}/{prefix}{year}/"
                    + (m["pdf"] if m["attr"].lower() == "xref" and m["pdf"] else m["file"]),
                }
        print(f"{label}: {len(rows) - before}", flush=True)

    def sort_key(r: dict) -> tuple:
        digits = re.match(r"\d+", r["number"])
        return (r["law_type"], int(digits.group()) if digits else 0, r["number"])

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(next(iter(rows.values())).keys()))
        writer.writeheader()
        writer.writerows(sorted(rows.values(), key=sort_key))
    print(f"Total: {len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()

"""Load scripts/law_index.csv into the law_index table (migration 009 must be run first).

    python scripts/load_law_index.py

Uses SEED_DATABASE_URL (owner role) from .env. Safe to re-run: rows are matched on
(law_type, number) and updated in place. Afterwards every listed law that has a
plain-English card in `laws` is linked to it.
"""
import csv
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parent.parent
CSV = Path(__file__).with_name("law_index.csv")
COLUMNS = ["law_type", "number", "label", "enacted_on", "year", "official_title", "source_url"]


def main():
    load_dotenv(ROOT / ".env")
    url = os.environ.get("SEED_DATABASE_URL")
    if not url:
        sys.exit("Missing SEED_DATABASE_URL (owner role) in .env")
    with CSV.open(encoding="utf-8") as f:
        rows = [
            (r["law_type"], r["number"], r["label"], r["enacted_on"] or None, int(r["year"]),
             r["official_title"], r["source_url"])
            for r in csv.DictReader(f)
        ]
    conn = psycopg2.connect(url)
    try:
        with conn, conn.cursor() as cur:
            execute_values(
                cur,
                f"INSERT INTO law_index ({', '.join(COLUMNS)}) VALUES %s "
                "ON CONFLICT (law_type, number) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[2:]),
                rows,
                page_size=1000,
            )
            # Link each card ("RA 10175") to its row in the list, and copy the card's titles
            # so a search for the everyday name ("Data Privacy Act") finds the law.
            cur.execute(
                "UPDATE law_index i SET law_id = l.id, "
                "common_name = l.official_title || ' / ' || l.plain_title FROM laws l "
                "WHERE i.law_type = 'ra' AND l.ra_number = 'RA ' || i.number "
                "AND (i.law_id IS DISTINCT FROM l.id "
                "OR i.common_name IS DISTINCT FROM l.official_title || ' / ' || l.plain_title)"
            )
            linked = cur.rowcount
            cur.execute("SELECT law_type, COUNT(*) FROM law_index GROUP BY law_type ORDER BY law_type")
            counts = cur.fetchall()
    finally:
        conn.close()
    print(f"Loaded {len(rows)} rows; linked {linked} to cards.")
    for law_type, n in counts:
        print(f"  {law_type}: {n}")


if __name__ == "__main__":
    main()

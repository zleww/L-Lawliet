"""Add a batch of plain-English guides to the laws table, then link them in the full list.

    python scripts/add_laws.py                 # loads scripts/seed_data_batch2.py
    python scripts/add_laws.py seed_data_batchN

Uses SEED_DATABASE_URL (owner role) from .env. Every record is validated with the API's own
LawCreate model first. Laws whose RA number is already in the table are skipped, so it is
safe to re-run.
"""
import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
from dotenv import load_dotenv

from _db import LAW_COLUMNS
from _models import LawCreate


def main():
    load_dotenv(os.path.join(ROOT, ".env"))
    url = os.environ.get("SEED_DATABASE_URL")
    if not url:
        sys.exit("Missing SEED_DATABASE_URL (owner role) in .env")
    module = importlib.import_module(sys.argv[1] if len(sys.argv) > 1 else "seed_data_batch2")
    records = [LawCreate(**law).model_dump() for law in module.LAWS]  # raises on any bad field
    cols = [c for c in LAW_COLUMNS if c in records[0]]
    added = []
    conn = psycopg2.connect(url)
    try:
        with conn, conn.cursor() as cur:
            for law in records:
                cur.execute(
                    f"INSERT INTO laws ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                    "ON CONFLICT (ra_number) DO NOTHING RETURNING id",
                    [law[c] for c in cols],
                )
                if cur.fetchone():
                    added.append(law["ra_number"])
            cur.execute(
                "UPDATE law_index i SET law_id = l.id, "
                "common_name = l.official_title || ' / ' || l.plain_title FROM laws l "
                "WHERE i.law_type = 'ra' AND l.ra_number = 'RA ' || i.number "
                "AND (i.law_id IS DISTINCT FROM l.id "
                "OR i.common_name IS DISTINCT FROM l.official_title || ' / ' || l.plain_title)"
            )
            linked = cur.rowcount
            cur.execute("SELECT COUNT(*) FROM laws")
            total = cur.fetchone()[0]
    finally:
        conn.close()
    skipped = len(records) - len(added)
    print(f"Added {len(added)} guides ({skipped} already there); linked {linked} in the full list. "
          f"Guides now: {total}.")


if __name__ == "__main__":
    main()

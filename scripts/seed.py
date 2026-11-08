"""One-time load of L-Lawliet's starting data into Neon.

Run from the project folder AFTER scripts/schema.sql:
    python scripts/seed.py

Reads from .env (never hardcoded):
    SEED_DATABASE_URL   owner-role connection string (falls back to DATABASE_URL)
    SEED_ADMIN_USERNAME / SEED_ADMIN_PASSWORD
    SEED_USER_USERNAME  / SEED_USER_PASSWORD

Refuses to run if the laws table already has rows, so it cannot duplicate data.
Every record is validated with the API's own LawCreate model before insert.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
from dotenv import load_dotenv

from _auth import hash_password
from _db import LAW_COLUMNS
from _models import LawCreate
from seed_data import LAWS


def need(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing {name} in .env")
    return value


def main():
    load_dotenv(os.path.join(ROOT, ".env"))
    url = os.environ.get("SEED_DATABASE_URL") or need("DATABASE_URL")
    accounts = [
        (need("SEED_ADMIN_USERNAME"), need("SEED_ADMIN_PASSWORD"), "admin"),
        (need("SEED_USER_USERNAME"), need("SEED_USER_PASSWORD"), "user"),
    ]
    for username, password, _ in accounts:
        if password == "CHANGE_ME" or len(password) < 8:
            sys.exit(f"Set a real password (8+ characters) for {username} in .env first.")

    laws = [LawCreate(**{k: v for k, v in law.items() if k in LAW_COLUMNS}).model_dump() for law in LAWS]
    notes = [(i + 1, n["user_name"], n["comment"]) for i, law in enumerate(LAWS) for n in law["user_notes"]]

    conn = psycopg2.connect(url)
    try:
        with conn, conn.cursor() as cur:  # one transaction: all or nothing
            cur.execute("SELECT COUNT(*) FROM laws")
            if cur.fetchone()[0] > 0:
                sys.exit("laws already has rows; seed not run again.")

            cols = ", ".join(LAW_COLUMNS)
            marks = ", ".join(["%s"] * len(LAW_COLUMNS))
            ids = []
            for law in laws:  # in list order, so SERIAL assigns 1..30
                cur.execute(f"INSERT INTO laws ({cols}) VALUES ({marks}) RETURNING id",
                            [law[c] for c in LAW_COLUMNS])
                ids.append(cur.fetchone()[0])

            for position, user_name, comment in notes:
                cur.execute("INSERT INTO comments (law_id, user_name, comment) VALUES (%s, %s, %s)",
                            (ids[position - 1], user_name, comment))

            for username, password, role in accounts:
                cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                            (username, hash_password(password), role))
    finally:
        conn.close()

    print(f"Seeded {len(ids)} laws (ids {ids[0]}-{ids[-1]}), {len(notes)} comment(s), {len(accounts)} accounts.")


if __name__ == "__main__":
    main()

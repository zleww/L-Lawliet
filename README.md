# L-Lawliet — The Central Legal Codex Backend & Explorer

> **Live Deployment:** [https://l-lawliet-three.vercel.app](https://l-lawliet-three.vercel.app)

L-Lawliet is the **Main Kitchen** (Central Backend API) for our 3 websites. It holds the master collection of Philippine Republic Acts and serves them over the internet to our other applications.

---

##  What This Project Does

- **Cloud Database:** All laws, community notes and user accounts live in **Neon PostgreSQL**. Nothing is hardcoded in the API.
- **Single Source of Truth:** JurisCard and JustGiveupATP fetch their data live from this API.
- **Explorer Website:** A dark navy and gold reference portal where users can read laws, search by keyword, and view detailed penalty breakdowns.
- **Access tiers:** guests see the first 10 laws; logged-in users see all of them and can add notes; admins can add, edit and delete laws.

---

##  API Endpoints

- **Live Base URL:** `https://l-lawliet-three.vercel.app/api/v1`
- **Interactive docs (Swagger UI):** `/api/docs`
- **Auth:** `POST /api/v1/auth/login` returns a token. Send it as `Authorization: Bearer <token>`. No token = guest.

| Method | Path | Access |
|---|---|---|
| GET | `/api/health` | Public (checks the database too) |
| GET | `/api/v1/law-index` | Public (full list of 19,000+ statutes: `q`, `type`, `year`, `page`, `per_page` up to 50) |
| POST | `/api/v1/auth/login` | Public (10 wrong passwords lock the account for 5 min) |
| POST | `/api/v1/auth/register` | Public (creates a `user` account) |
| POST | `/api/v1/auth/google` | Public (Sign in with Google; needs `GOOGLE_CLIENT_ID`) |
| GET | `/api/v1/auth/config` | Public (Google client ID for the login page) |
| GET / PATCH | `/api/v1/me` | User or Admin (own profile: display name, bio, theme, accent) |
| POST | `/api/v1/me/password` | User or Admin (signs out other devices) |
| DELETE | `/api/v1/me` | User or Admin (own account; notes stay as "Deleted user") |
| POST | `/api/v1/auth/logout-all` | User or Admin (every token for the account stops working) |
| PATCH | `/api/v1/comments/{id}` | The note's author only |
| DELETE | `/api/v1/comments/{id}` | The note's author, or an admin |
| GET | `/api/v1/me/saved` | User or Admin (own saved laws) |
| POST / DELETE | `/api/v1/laws/{id}/save` | User or Admin (save / unsave a law) |
| PUT / DELETE | `/api/v1/laws/{id}/rating` | User or Admin (one 1-5 rating per law) |
| POST / DELETE | `/api/v1/comments/{id}/vote` | User or Admin (mark someone else's note helpful) |
| POST | `/api/v1/comments/{id}/report` | User or Admin (report someone else's note) |
| POST | `/api/v1/suggestions` | User or Admin (suggest a missing law) |
| GET | `/api/v1/me/suggestions` | User or Admin (own suggestions and their status) |
| GET | `/api/v1/users/{id}` | User or Admin (public profile: name, bio, notes) |
| GET / PATCH | `/api/v1/admin/reports[/{id}]` | Admin (report queue; dismiss) |
| GET / PATCH | `/api/v1/admin/suggestions[/{id}]` | Admin (review: approve with the new law's id, or reject) |
| GET | `/api/v1/admin/users` | Admin (account list) |
| POST | `/api/v1/admin/users/{id}/unlock`, `/logout-all` | Admin |
| DELETE | `/api/v1/admin/users/{id}` | Admin (non-admin accounts only) |
| GET | `/api/v1/stats` | Public (counts only) |
| GET | `/api/v1/laws?category=&search=` | Guest: first 10 · User/Admin: all |
| GET | `/api/v1/laws/search?q=` | Guest: first 10 · User/Admin: all |
| GET | `/api/v1/laws/{id}` | Guest: first 10 · User/Admin: all |
| POST | `/api/v1/laws/{id}/comments` | User or Admin |
| POST | `/api/v1/laws` | Admin |
| PATCH | `/api/v1/laws/{id}` | Admin |
| DELETE | `/api/v1/laws/{id}` | Admin |

The legacy `/api/laws...` read paths still work for JurisCard and JustGiveupATP (as guests).

---

##  Setup (first time)

1. **Neon:** in the SQL Editor (owner role), run `scripts/schema.sql`. Create a role `lawliet_app` on the Roles page, then run `scripts/grants.sql`.
2. **Secrets:** copy `.env.example` to `.env` and fill in real values. `.env` is git-ignored.
3. **Install:** `pip install -r requirements.txt`
4. **Seed (once):** `python scripts/seed.py` loads the 30 laws, the existing note and the two test accounts.
5. **Accounts and security rules:** run `scripts/migrate_002_accounts.sql` (owner role), deploy the code, then run `scripts/migrate_003_security_rules.sql` (Row-Level Security) and `scripts/migrate_004_comment_delete.sql`. Run `scripts/migrate_005_user_features.sql` BEFORE deploying the code that uses it (saved laws, ratings, votes, reports, suggestions, admin account tools). In that order: the old code cannot write once 003 is on.
6. **Full list of laws:** run `scripts/migrate_009_law_index.sql` (owner role) before deploying the code, then `python scripts/load_law_index.py` to load `scripts/law_index.csv`. To refresh the list (new laws each year), run `python scripts/fetch_law_index.py <cache-folder>`, then the loader again. Then run PART A of `scripts/migrate_010_all_laws.sql`, deploy, and run PART B: every listed law becomes a law people can save, rate and comment on (lists of guides stay guides only). New plain-English guides go in a batch file such as `scripts/seed_data_batch2.py` and are loaded with `python scripts/add_laws.py`.
7. **Run locally:** `python scripts/dev.py`, then open http://127.0.0.1:8000 (site) and http://127.0.0.1:8000/api/docs (API).
8. **Vercel:** add `DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `ALLOWED_ORIGINS` and (for Google sign-in) `GOOGLE_CLIENT_ID` under Project Settings → Environment Variables (Production and Preview). The function region is set to Singapore (`sin1`) in `vercel.json`.

##  How to Update Laws

Laws are now data, not code. Log in as an admin and use `admin.html`, or call the admin endpoints from `/api/docs`. No redeploy is needed.

##  How to Update the Code (Git Bash)

```bash
git add -A
git commit -m "describe the change"
git push origin main
```

##  Database Diagram (ERD)

One Neon PostgreSQL database serves L-Lawliet, JurisCards and JurisCards Arena: 16 tables and 23 foreign keys, with Row-Level Security on every table.

![L-Lawliet database ERD](report-screenshots/ERD%20-%20L-Lawliet%20database%20(updated%202026-11-24).png)

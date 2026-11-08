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
| POST | `/api/v1/auth/login` | Public |
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
5. **Run locally:** `python scripts/dev.py`, then open http://127.0.0.1:8000 (site) and http://127.0.0.1:8000/api/docs (API).
6. **Vercel:** add `DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES` and `ALLOWED_ORIGINS` under Project Settings → Environment Variables (Production and Preview). The function region is set to Singapore (`sin1`) in `vercel.json`.

##  How to Update Laws

Laws are now data, not code. Log in as an admin and use `admin.html`, or call the admin endpoints from `/api/docs`. No redeploy is needed.

##  How to Update the Code (Git Bash)

```bash
git add -A
git commit -m "describe the change"
git push origin main
```

# L-Lawliet — The Central Legal Codex Backend & Explorer

> **Live Deployment:** [https://l-lawliet-three.vercel.app](https://l-lawliet-three.vercel.app)

L-Lawliet is the **Main Kitchen** (Central Backend API) for our 3 websites. It holds the master collection of Philippine Republic Acts and serves them over the internet to our other applications.

---

##  What This Project Does

- **Master Database:** Stores and validates all Republic Acts using Python FastAPI.
- **Single Source of Truth:** JurisCard and JustGiveupATP fetch their data live from this repository.
- **Explorer Website:** A dark navy and gold reference portal where users can read laws, search by keyword, and view detailed penalty breakdowns.

---

##  API Endpoints

- **Live Base URL:** `https://l-lawliet-three.vercel.app/api/v1`
- **All Laws:** `GET /api/v1/laws` (Requires Header `x-api-key: student-api-key-123`)
- **Single Law:** `GET /api/v1/laws/{id}`
- **System Health:** `GET /health` (Public)

---

##  How to Update Laws (Git Bash)

Whenever you edit or add laws in `api/index.py`, run these commands to update all 3 websites at once:

```bash
# 1. Stage the changes
git add api/index.py

# 2. Save your commit message
git commit -m "feat: add new laws to central database"

# 3. Push live to GitHub & Vercel
git push origin main

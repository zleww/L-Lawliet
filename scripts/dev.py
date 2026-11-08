"""Local development server: the API plus the static site on one address.

    python scripts/dev.py   ->  http://127.0.0.1:8000  (site)   /api/docs  (API)

Vercel serves the static files itself, so this file is never deployed as part of the API.
Only whitelisted file types are served, so .env and source files are never exposed.
"""
import os
import sys

ROOT = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "api"))
os.chdir(ROOT)

import uvicorn
from fastapi import HTTPException
from fastapi.responses import FileResponse

from index import app

PUBLIC_EXTENSIONS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(os.path.join(ROOT, "index.html"))


@app.get("/{path:path}", include_in_schema=False)
def static_file(path: str):
    full = os.path.realpath(os.path.join(ROOT, path))
    ext = os.path.splitext(full)[1].lower()
    if (not full.startswith(ROOT + os.sep) or ext not in PUBLIC_EXTENSIONS
            or os.sep + "scripts" + os.sep in full or not os.path.isfile(full)):
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(full)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

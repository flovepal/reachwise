"""Reachwise API server.

Run on the lab machine:
    uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
and expose it with Cloudflare Tunnel (see README).
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import jobs
from .config import settings
from .db import get_db
from .routers import auth, campaign, documents, emails, me, professors, replies

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_db()  # connect + create indexes
    if settings.run_scheduler:
        jobs.start()
    yield
    jobs.stop()


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)

# The app authenticates with a bearer token (no cookies), so any origin is fine.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, me.router, professors.router, documents.router, campaign.router, emails.router,
          replies.router):
    app.include_router(r)


@app.get("/health")
def health():
    get_db().command("ping")
    return {"ok": True, "app": settings.app_name}


@app.get("/config")
def public_config():
    """Non-secret settings the app shows to students."""
    return {
        "app_name": settings.app_name,
        "google_web_client_id": settings.google_web_client_id,
        "reminder_after_days": settings.reminder_after_days,
        "max_reminders": settings.max_reminders,
        "daily_cap": settings.daily_cap,
        "gap_seconds": [settings.min_gap_seconds, settings.max_gap_seconds],
        "goals": [{"id": "teep", "name": "TEEP internship"}, {"id": "iipp", "name": "IIPP internship"},
                  {"id": "admission", "name": "Admission (Master's / PhD)"}],
        "dev_login": settings.dev_login,
    }


# ---- the website (built into backend/web by `npm run build` in ../web) ------
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if (WEB_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def website():
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(WEB_DIR / "favicon.svg")

    @app.get("/config.js", include_in_schema=False)
    def site_config():
        return FileResponse(WEB_DIR / "config.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

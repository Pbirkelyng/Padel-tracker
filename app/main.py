from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.bootstrap import bootstrap_admin, init_db
from app.db import SessionLocal
from app.middleware import AuthRedirectMiddleware
from app.routers import admin, auth, invites, leaderboard, leagues, matches, schedule

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Padel Tracker", lifespan=lifespan)
app.add_middleware(AuthRedirectMiddleware)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(invites.router)
app.include_router(leagues.router)
app.include_router(schedule.router)
app.include_router(matches.router)
app.include_router(leaderboard.router)
app.include_router(admin.router)


@app.get("/manifest.webmanifest")
def manifest():
    return {
        "name": "Padel Tracker",
        "short_name": "Padel",
        "description": "Track padel matches, scores, and rankings",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f8fafc",
        "theme_color": "#2563eb",
        "icons": [
            {
                "src": "/static/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
            },
        ],
    }

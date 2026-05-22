from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ApprovedUser
from app.league_helpers import (
    get_league_by_slug,
    is_league_admin,
    nav_pending_for_league,
    require_membership,
)
from app.models import Season
from app.services.seasons import end_current_season
from app.services.stats import compute_leaderboard, sort_leaderboard
from app.templating import templates

router = APIRouter(tags=["leaderboard"], prefix="/leagues/{slug}")


@router.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page(
    request: Request,
    slug: str,
    user: ApprovedUser,
    db: Session = Depends(get_db),
    sort: str = "rating",
    season: str | None = None,
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    mem = require_membership(db, league, user.id)

    seasons_list = db.scalars(
        select(Season).where(Season.league_id == league.id).order_by(Season.id.desc())
    ).all()

    target_season = None
    if season and season != "current":
        try:
            sid = int(season)
            target_season = next((s for s in seasons_list if s.id == sid), None)
        except ValueError:
            target_season = None
    if target_season is None:
        target_season = seasons_list[0] if seasons_list else None

    nav_pending = nav_pending_for_league(db, league, user.id)
    if not target_season:
        return templates.TemplateResponse(
            request,
            "leaderboard/index.html",
            {
                "user": user,
                "league": league,
                "league_slug": slug,
                "rows": [],
                "sort": sort,
                "seasons": seasons_list,
                "selected_season_id": None,
                "is_league_admin": is_league_admin(mem),
                "is_current_season": False,
                "season_qs": "",
                "nav_members_pending": nav_pending,
            },
        )

    season_qs = f"&season={target_season.id}"
    rows = compute_leaderboard(db, league.id, target_season)
    rows = sort_leaderboard(rows, sort)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "leaderboard/_table.html",
            {
                "user": user,
                "rows": rows,
                "sort": sort,
                "league_slug": slug,
                "selected_season_id": target_season.id,
                "season_qs": season_qs,
            },
        )

    return templates.TemplateResponse(
        request,
        "leaderboard/index.html",
        {
            "user": user,
            "league": league,
            "league_slug": slug,
            "rows": rows,
            "sort": sort,
            "seasons": seasons_list,
            "selected_season_id": target_season.id,
            "is_league_admin": is_league_admin(mem),
            "is_current_season": target_season.is_current,
            "season_qs": season_qs,
            "nav_members_pending": nav_pending,
        },
    )


@router.post("/leaderboard/end-season")
def end_season_form(
    slug: str,
    actor: ApprovedUser,
    db: Session = Depends(get_db),
    confirm_end: str = Form(""),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    mem = require_membership(db, league, actor.id)
    if not is_league_admin(mem) or confirm_end != "yes":
        return RedirectResponse(f"/leagues/{slug}/leaderboard", status_code=303)
    try:
        end_current_season(db, league)
        db.commit()
    except ValueError:
        db.rollback()
    return RedirectResponse(f"/leagues/{slug}/leaderboard", status_code=303)

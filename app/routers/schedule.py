from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import ApprovedUser
from app.league_helpers import (
    current_season,
    get_active_membership,
    get_league_by_slug,
    require_membership,
)
from app.models import (
    League,
    LeagueMember,
    LeagueMemberStatus,
    Match,
    MatchPlayer,
    MatchStatus,
    User,
    UserStatus,
)
from app.templating import templates

router = APIRouter(tags=["schedule"], prefix="/leagues/{slug}")


def _score_summary(match: Match) -> str:
    if not match.set_scores:
        return ""
    parts = []
    for s in match.set_scores:
        tb = ""
        if s.team_a_games == 7 and s.team_b_games == 6 and s.team_a_tb:
            tb = f" ({s.team_a_tb})"
        elif s.team_b_games == 7 and s.team_a_games == 6 and s.team_b_tb:
            tb = f" ({s.team_b_tb})"
        parts.append(f"{s.team_a_games}-{s.team_b_games}{tb}")
    return ", ".join(parts)


@router.get("/schedule", response_class=HTMLResponse)
def schedule_page(
    request: Request,
    slug: str,
    user: ApprovedUser,
    db: Session = Depends(get_db),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    require_membership(db, league, user.id)
    now = datetime.utcnow()
    matches = db.scalars(
        select(Match)
        .where(Match.league_id == league.id)
        .options(
            selectinload(Match.players).selectinload(MatchPlayer.user),
            selectinload(Match.set_scores),
        )
        .order_by(Match.scheduled_at.desc())
    ).all()

    upcoming = [
        m
        for m in matches
        if m.status == MatchStatus.scheduled and m.scheduled_at >= now
    ]
    upcoming.sort(key=lambda m: m.scheduled_at)
    past = [
        m
        for m in matches
        if m.status == MatchStatus.completed
        or (m.status == MatchStatus.scheduled and m.scheduled_at < now)
    ]

    for m in past:
        m.score_summary = _score_summary(m)  # type: ignore[attr-defined]

    return templates.TemplateResponse(
        request,
        "schedule/index.html",
        {
            "user": user,
            "league": league,
            "league_slug": slug,
            "upcoming": upcoming,
            "past": past,
        },
    )


@router.get("/matches/new", response_class=HTMLResponse)
def new_match_page(slug: str, request: Request, user: ApprovedUser, db: Session = Depends(get_db)):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    require_membership(db, league, user.id)

    members = db.scalars(
        select(LeagueMember)
        .where(
            LeagueMember.league_id == league.id,
            LeagueMember.status == LeagueMemberStatus.active,
        )
        .options(selectinload(LeagueMember.user))
        .order_by(LeagueMember.joined_at)
    ).all()
    roster = [(m.user, m.rating) for m in members if m.user.status == UserStatus.approved]

    return templates.TemplateResponse(
        request,
        "schedule/new_match.html",
        {"user": user, "roster": roster, "error": None, "league": league, "league_slug": slug},
    )


@router.post("/matches")
def create_match(
    request: Request,
    slug: str,
    user: ApprovedUser,
    scheduled_date: str = Form(...),
    scheduled_time: str = Form(...),
    location: str = Form(""),
    best_of: int = Form(3),
    player_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    require_membership(db, league, user.id)

    season_obj = current_season(db, league.id)
    if not season_obj:
        return RedirectResponse(f"/leagues/{slug}/schedule", status_code=303)

    if best_of not in (3, 5, 7):
        best_of = 3

    try:
        scheduled_at = datetime.strptime(f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        members = db.scalars(
            select(LeagueMember).where(
                LeagueMember.league_id == league.id,
                LeagueMember.status == LeagueMemberStatus.active,
            ).options(selectinload(LeagueMember.user))
        ).all()
        roster = [(m.user, m.rating) for m in members]
        return templates.TemplateResponse(
            request,
            "schedule/new_match.html",
            {"user": user, "roster": roster, "error": "Invalid date or time", "league": league, "league_slug": slug},
            status_code=400,
        )

    ids = list({int(pid) for pid in player_ids})
    if user.id not in ids:
        ids.append(user.id)
    if len(ids) > 4:
        members = db.scalars(
            select(LeagueMember).where(
                LeagueMember.league_id == league.id,
                LeagueMember.status == LeagueMemberStatus.active,
            ).options(selectinload(LeagueMember.user))
        ).all()
        roster = [(m.user, m.rating) for m in members]
        return templates.TemplateResponse(
            request,
            "schedule/new_match.html",
            {"user": user, "roster": roster, "error": "Maximum 4 players per match", "league": league, "league_slug": slug},
            status_code=400,
        )

    for pid in ids:
        if not get_active_membership(db, league.id, pid):
            return RedirectResponse(f"/leagues/{slug}/matches/new", status_code=303)

    match = Match(
        scheduled_at=scheduled_at,
        location=location.strip() or None,
        best_of=best_of,
        status=MatchStatus.scheduled,
        league_id=league.id,
        season_id=season_obj.id,
        created_by_id=user.id,
    )
    db.add(match)
    db.flush()

    for pid in ids:
        db.add(MatchPlayer(match_id=match.id, user_id=pid, team=None))

    db.commit()
    return RedirectResponse(f"/matches/{match.id}", status_code=303)

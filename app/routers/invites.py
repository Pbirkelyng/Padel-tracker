from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import ApprovedUser, get_current_user_optional
from app.league_helpers import get_active_membership
from app.models import LeagueInvite, LeagueMember, LeagueMemberRole, LeagueMemberStatus, UserStatus
from app.models.user import User
from app.templating import templates

router = APIRouter(tags=["invites"])

MAX_AGE_DAYS = 30


def _inv_age_days(inv: LeagueInvite) -> int:
    if not inv.created_at:
        return 0
    c = inv.created_at
    if c.tzinfo is not None:
        c = c.replace(tzinfo=None)
    return (datetime.utcnow() - c).days


@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_page(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    inv = db.scalar(select(LeagueInvite).where(LeagueInvite.token == token).options(joinedload(LeagueInvite.league)))
    if not inv:
        return templates.TemplateResponse(request, "invites/invalid.html", {"error": "Invalid link"})
    if inv.accepted_at is not None:
        return templates.TemplateResponse(
            request, "invites/invalid.html", {"error": "This invite has already been used"}
        )

    league = inv.league
    if league is None:
        return RedirectResponse("/", status_code=303)

    if _inv_age_days(inv) > MAX_AGE_DAYS:
        return templates.TemplateResponse(
            request, "invites/invalid.html", {"error": "This invite link has expired"}
        )

    if not user:
        return RedirectResponse(f"/login?next=/invite/{token}", status_code=303)
    if user.status == UserStatus.pending:
        return RedirectResponse("/pending", status_code=303)
    if user.status == UserStatus.rejected:
        return RedirectResponse("/login?error=rejected", status_code=303)

    if get_active_membership(db, league.id, user.id):
        return RedirectResponse(f"/leagues/{league.slug}/schedule", status_code=303)

    pend = db.scalar(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.user_id == user.id,
            LeagueMember.status == LeagueMemberStatus.pending_request,
        )
    )
    return templates.TemplateResponse(
        request,
        "invites/accept.html",
        {
            "user": user,
            "league": league,
            "league_slug": league.slug,
            "token": token,
            "pending_membership": pend,
        },
    )


@router.post("/invite/{token}/accept")
def invite_accept(token: str, user: ApprovedUser, db: Session = Depends(get_db)):
    inv = db.scalar(select(LeagueInvite).where(LeagueInvite.token == token).options(joinedload(LeagueInvite.league)))
    if not inv or inv.accepted_at is not None or _inv_age_days(inv) > MAX_AGE_DAYS:
        return RedirectResponse("/", status_code=303)
    league = inv.league
    if league is None:
        return RedirectResponse("/", status_code=303)

    if get_active_membership(db, league.id, user.id):
        return RedirectResponse(f"/leagues/{league.slug}/schedule", status_code=303)

    pend = db.scalar(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.user_id == user.id,
            LeagueMember.status == LeagueMemberStatus.pending_request,
        )
    )
    if pend:
        pend.status = LeagueMemberStatus.active
    else:
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role=LeagueMemberRole.member,
                status=LeagueMemberStatus.active,
                rating=1000.0,
            )
        )
    inv.accepted_at = datetime.utcnow()
    inv.accepted_by_id = user.id
    db.commit()
    return RedirectResponse(f"/leagues/{league.slug}/schedule", status_code=303)

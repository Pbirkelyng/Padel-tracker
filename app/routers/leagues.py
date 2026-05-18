import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import AdminUser, ApprovedUser
from app.league_helpers import (
    create_placeholder_member,
    get_active_membership,
    get_league_by_slug,
    is_league_admin,
    link_placeholder_to_user,
    match_count_by_league,
    memberships_for_home,
    next_league_slug,
    pending_join_count_for_admin,
    require_membership,
)
from app.models import (
    League,
    LeagueInvite,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    Season,
    User,
    UserStatus,
)
from app.templating import templates
from app.utils.slug import slugify

router = APIRouter(tags=["leagues"])


@router.get("/", response_class=HTMLResponse)
def frontpage(request: Request, user: ApprovedUser, db: Session = Depends(get_db)):
    pairs = memberships_for_home(db, user.id)
    my_ids = {lg.id for lg, _ in pairs}
    q = select(League).where(League.is_public.is_(True))
    if my_ids:
        q = q.where(~League.id.in_(my_ids))
    leagues_public = db.scalars(q.order_by(League.name)).all()

    mc = match_count_by_league(db, set(my_ids))
    pend = pending_join_count_for_admin(db, user.id)

    return templates.TemplateResponse(
        request,
        "leagues/index.html",
        {
            "user": user,
            "league_slug": "",
            "my_leagues": pairs,
            "discover_leagues": leagues_public,
            "match_counts": mc,
            "pending_admin_count": pend,
            "year": datetime.utcnow().year,
        },
    )


@router.get("/leagues/new", response_class=HTMLResponse)
def new_league_page(request: Request, user: AdminUser, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "leagues/new.html",
        {"user": user, "league_slug": "", "error": None},
    )


@router.post("/leagues")
def create_league(
    request: Request,
    user: AdminUser,
    name: str = Form(...),
    description: str = Form(""),
    is_public: str = Form("on"),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if len(name) < 2 or len(name) > 100:
        return templates.TemplateResponse(
            request,
            "leagues/new.html",
            {"user": user, "league_slug": "", "error": "Name must be 2–100 characters"},
            status_code=400,
        )

    pub = is_public == "on"
    base_slug = slugify(name)
    slug = next_league_slug(db, base_slug)

    league = League(
        name=name,
        slug=slug,
        description=description.strip()[:500],
        is_public=pub,
        created_by_id=user.id,
    )
    db.add(league)
    db.flush()

    season = Season(league_id=league.id, name="Season 1", is_current=True)
    db.add(season)

    mem = LeagueMember(
        league_id=league.id,
        user_id=user.id,
        role=LeagueMemberRole.admin,
        status=LeagueMemberStatus.active,
        rating=1000.0,
        is_pinned=False,
    )
    db.add(mem)
    db.commit()
    return RedirectResponse(f"/leagues/{league.slug}", status_code=303)


@router.get("/leagues/{slug}", response_class=HTMLResponse)
def league_hub(
    request: Request,
    slug: str,
    user: ApprovedUser,
    db: Session = Depends(get_db),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    require_membership(db, league, user.id)
    return RedirectResponse(f"/leagues/{slug}/schedule", status_code=303)


@router.post("/leagues/{slug}/join-request")
def request_join_public_league(slug: str, user: ApprovedUser, db: Session = Depends(get_db)):
    league = get_league_by_slug(db, slug)
    if not league or not league.is_public:
        return RedirectResponse("/", status_code=303)
    existing = get_active_membership(db, league.id, user.id)
    if existing:
        return RedirectResponse(f"/leagues/{slug}/schedule", status_code=303)
    pend = db.scalar(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.user_id == user.id,
            LeagueMember.status == LeagueMemberStatus.pending_request,
        )
    )
    if pend:
        return RedirectResponse("/", status_code=303)
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=user.id,
            role=LeagueMemberRole.member,
            status=LeagueMemberStatus.pending_request,
            rating=1000.0,
        )
    )
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/leagues/{slug}/members/{user_id}/approve")
def approve_member(
    slug: str,
    user_id: int,
    actor: ApprovedUser,
    db: Session = Depends(get_db),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, actor.id)
    if not is_league_admin(me):
        return RedirectResponse("/", status_code=303)
    m = db.scalar(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.user_id == user_id,
            LeagueMember.status == LeagueMemberStatus.pending_request,
        )
    )
    if m:
        m.status = LeagueMemberStatus.active
        db.commit()
    return RedirectResponse(f"/leagues/{slug}/members", status_code=303)


@router.post("/leagues/{slug}/members/{user_id}/reject")
def reject_member(
    slug: str,
    user_id: int,
    actor: ApprovedUser,
    db: Session = Depends(get_db),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, actor.id)
    if not is_league_admin(me):
        return RedirectResponse("/", status_code=303)
    m = db.scalar(
        select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.user_id == user_id,
        )
    )
    if m and m.status == LeagueMemberStatus.pending_request:
        db.delete(m)
        db.commit()
    return RedirectResponse(f"/leagues/{slug}/members", status_code=303)


@router.get("/leagues/{slug}/members", response_class=HTMLResponse)
def members_page(slug: str, request: Request, user: ApprovedUser, db: Session = Depends(get_db)):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    membership = require_membership(db, league, user.id)
    pend = []
    admin = is_league_admin(membership)
    if admin:
        pend = db.scalars(
            select(LeagueMember)
            .where(
                LeagueMember.league_id == league.id,
                LeagueMember.status == LeagueMemberStatus.pending_request,
            )
            .options(joinedload(LeagueMember.user))
        ).all()

    active_members = db.scalars(
        select(LeagueMember)
        .where(
            LeagueMember.league_id == league.id,
            LeagueMember.status == LeagueMemberStatus.active,
        )
        .options(joinedload(LeagueMember.user))
        .order_by(LeagueMember.joined_at)
    ).all()

    invites = []
    link_candidates: list[User] = []
    if admin:
        invites = db.scalars(
            select(LeagueInvite).where(
                LeagueInvite.league_id == league.id,
                LeagueInvite.accepted_at.is_(None),
            ).order_by(LeagueInvite.created_at.desc()).limit(20)
        ).all()

        # Registered users not already in this league — candidates that an
        # admin can link a placeholder to.
        member_user_ids = {m.user_id for m in active_members}
        link_candidates = db.scalars(
            select(User)
            .where(
                User.is_placeholder.is_(False),
                User.status == UserStatus.approved,
                ~User.id.in_(member_user_ids) if member_user_ids else User.id.is_not(None),
            )
            .order_by(User.display_name)
        ).all()

    return templates.TemplateResponse(
        request,
        "leagues/members.html",
        {
            "user": user,
            "league": league,
            "league_slug": slug,
            "membership": membership,
            "pending": pend,
            "members": active_members,
            "invites": invites,
            "link_candidates": link_candidates,
            "is_admin": admin,
        },
    )


@router.post("/leagues/{slug}/members/placeholder")
def add_placeholder_member(
    slug: str,
    actor: ApprovedUser,
    db: Session = Depends(get_db),
    display_name: str = Form(...),
    email_hint: str = Form(""),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, actor.id)
    if not is_league_admin(me):
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)

    name = display_name.strip()[:100]
    if len(name) < 1:
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)

    create_placeholder_member(db, league.id, name, email_hint)
    db.commit()
    return RedirectResponse(f"/leagues/{slug}/members", status_code=303)


@router.post("/leagues/{slug}/members/{user_id}/edit-placeholder")
def edit_placeholder_member(
    slug: str,
    user_id: int,
    actor: ApprovedUser,
    db: Session = Depends(get_db),
    display_name: str = Form(...),
    email_hint: str = Form(""),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, actor.id)
    if not is_league_admin(me):
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)

    target = db.get(User, user_id)
    if not target or not target.is_placeholder:
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)
    # Make sure the placeholder belongs to this league before mutating.
    if not get_active_membership(db, league.id, user_id):
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)

    name = display_name.strip()[:100]
    if name:
        target.display_name = name
    hint = email_hint.strip()[:255]
    target.placeholder_email_hint = hint or None
    db.commit()
    return RedirectResponse(f"/leagues/{slug}/members", status_code=303)


@router.post("/leagues/{slug}/members/{user_id}/delete-placeholder")
def delete_placeholder_member(
    slug: str,
    user_id: int,
    actor: ApprovedUser,
    db: Session = Depends(get_db),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, actor.id)
    if not is_league_admin(me):
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)

    target = db.get(User, user_id)
    if not target or not target.is_placeholder:
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)

    # Delete the placeholder entirely (cascades remove its memberships and
    # match-player rows via ON DELETE behaviour — but match_players doesn't
    # cascade on user, so we clean it up explicitly to avoid orphan FKs).
    from app.models import MatchPlayer

    for mp in db.scalars(select(MatchPlayer).where(MatchPlayer.user_id == target.id)).all():
        db.delete(mp)
    for lm in db.scalars(select(LeagueMember).where(LeagueMember.user_id == target.id)).all():
        db.delete(lm)
    db.delete(target)
    db.commit()
    return RedirectResponse(f"/leagues/{slug}/members", status_code=303)


@router.post("/leagues/{slug}/members/{user_id}/link")
def link_placeholder_member(
    slug: str,
    user_id: int,
    actor: ApprovedUser,
    db: Session = Depends(get_db),
    real_user_id: int = Form(...),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, actor.id)
    if not is_league_admin(me):
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)

    ok = link_placeholder_to_user(db, user_id, real_user_id)
    if ok:
        db.commit()
    else:
        db.rollback()
    return RedirectResponse(f"/leagues/{slug}/members", status_code=303)


@router.post("/leagues/{slug}/invites")
def create_invite(
    slug: str,
    user: ApprovedUser,
    db: Session = Depends(get_db),
    email_hint: str = Form(""),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, user.id)
    if not is_league_admin(me):
        return RedirectResponse(f"/leagues/{slug}/members", status_code=303)
    tok = secrets.token_urlsafe(32)
    db.add(
        LeagueInvite(
            league_id=league.id,
            email=email_hint.strip()[:255],
            token=tok,
            created_by_id=user.id,
        )
    )
    db.commit()
    return RedirectResponse(f"/leagues/{slug}/members", status_code=303)


@router.post("/leagues/{slug}/rename")
def rename_league(
    slug: str,
    user: ApprovedUser,
    db: Session = Depends(get_db),
    name: str = Form(...),
):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, user.id)
    if not is_league_admin(me):
        return RedirectResponse("/", status_code=303)
    name = name.strip()
    if 2 <= len(name) <= 100:
        league.name = name
        db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/leagues/{slug}/delete")
def delete_league(slug: str, user: ApprovedUser, db: Session = Depends(get_db), confirm: str = Form("")):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    me = require_membership(db, league, user.id)
    if not is_league_admin(me):
        return RedirectResponse("/", status_code=303)
    if confirm.strip() != league.name:
        return RedirectResponse("/", status_code=303)

    db.delete(league)
    db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/leagues/{slug}/pin")
def toggle_pin(slug: str, user: ApprovedUser, db: Session = Depends(get_db)):
    league = get_league_by_slug(db, slug)
    if not league:
        return RedirectResponse("/", status_code=303)
    m = require_membership(db, league, user.id)
    m.is_pinned = not m.is_pinned
    db.commit()
    return RedirectResponse("/", status_code=303)


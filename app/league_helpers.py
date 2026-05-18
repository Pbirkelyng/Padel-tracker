import secrets

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    Match,
    MatchPlayer,
    Season,
    User,
    UserStatus,
)


def get_league_by_slug(db: Session, slug: str) -> League | None:
    return db.scalar(select(League).where(League.slug == slug))


def get_active_membership(db: Session, league_id: int, user_id: int) -> LeagueMember | None:
    return db.scalar(
        select(LeagueMember).where(
            LeagueMember.league_id == league_id,
            LeagueMember.user_id == user_id,
            LeagueMember.status == LeagueMemberStatus.active,
        )
    )


def require_membership(db: Session, league: League, user_id: int) -> LeagueMember:
    m = get_active_membership(db, league.id, user_id)
    if not m:
        raise HTTPException(status_code=403, detail="Not a league member")
    return m


def is_league_admin(membership: LeagueMember) -> bool:
    return membership.role == LeagueMemberRole.admin


def current_season(db: Session, league_id: int) -> Season | None:
    return db.scalar(
        select(Season).where(Season.league_id == league_id, Season.is_current.is_(True))
    )


def next_league_slug(db: Session, base: str) -> str:
    cand = base
    n = 0
    while db.scalar(select(League).where(League.slug == cand)):
        n += 1
        cand = f"{base}-{n}"
    return cand


def match_count_by_league(db: Session, league_ids: set[int]) -> dict[int, int]:
    if not league_ids:
        return {}
    rows = db.execute(
        select(Match.league_id, func.count(Match.id))
        .where(Match.league_id.in_(league_ids))
        .group_by(Match.league_id)
    ).all()
    return {lid: int(c) for lid, c in rows}


def pending_join_count_for_admin(db: Session, admin_user_id: int) -> int:
    admin_league_ids = db.scalars(
        select(LeagueMember.league_id).where(
            LeagueMember.user_id == admin_user_id,
            LeagueMember.role == LeagueMemberRole.admin,
            LeagueMember.status == LeagueMemberStatus.active,
        )
    ).all()
    if not admin_league_ids:
        return 0
    return db.scalar(
        select(func.count())
        .select_from(LeagueMember)
        .where(
            LeagueMember.league_id.in_(admin_league_ids),
            LeagueMember.status == LeagueMemberStatus.pending_request,
        )
    ) or 0


def create_placeholder_member(
    db: Session,
    league_id: int,
    display_name: str,
    email_hint: str | None,
) -> LeagueMember:
    """Create a placeholder User + LeagueMember in one go.

    Placeholders are non-loginable stub accounts that let admins put names on
    matches before the real person signs up. Use ``link_placeholder_to_user``
    to merge a placeholder into a registered account later.
    """
    synthetic_email = f"placeholder-{secrets.token_urlsafe(12)}@local.placeholder"
    stub = User(
        email=synthetic_email,
        password_hash="",
        display_name=display_name.strip()[:100] or "Placeholder",
        status=UserStatus.approved,
        is_admin=False,
        is_placeholder=True,
        placeholder_email_hint=(email_hint or "").strip()[:255] or None,
    )
    db.add(stub)
    db.flush()
    member = LeagueMember(
        league_id=league_id,
        user_id=stub.id,
        role=LeagueMemberRole.member,
        status=LeagueMemberStatus.active,
        rating=1000.0,
        is_pinned=False,
    )
    db.add(member)
    db.flush()
    return member


def link_placeholder_to_user(
    db: Session,
    placeholder_user_id: int,
    real_user_id: int,
) -> bool:
    """Merge a placeholder User into a registered User.

    Transfers all league memberships, match players, and match-creator
    references from the placeholder to the real user, then deletes the
    placeholder. Returns True on success, False if inputs are invalid.
    """
    placeholder = db.get(User, placeholder_user_id)
    real = db.get(User, real_user_id)
    if not placeholder or not real:
        return False
    if not placeholder.is_placeholder or real.is_placeholder:
        return False
    if placeholder.id == real.id:
        return False

    # League memberships: if the real user already has a row in this league
    # (active member, or a pending join request), inherit the placeholder's
    # active status and accumulated rating onto that row and drop the
    # placeholder's. Otherwise, just reassign the placeholder's membership
    # to the real user.
    placeholder_memberships = db.scalars(
        select(LeagueMember).where(LeagueMember.user_id == placeholder.id)
    ).all()
    for pm in placeholder_memberships:
        existing = db.scalar(
            select(LeagueMember).where(
                LeagueMember.league_id == pm.league_id,
                LeagueMember.user_id == real.id,
            )
        )
        if existing:
            existing.status = LeagueMemberStatus.active
            existing.rating = pm.rating
            # Keep existing.role and existing.is_pinned — the real user's
            # own choices for this league shouldn't be overwritten.
            db.delete(pm)
        else:
            pm.user_id = real.id

    # Match players: same collision handling — if the real user is already on
    # the match, drop the placeholder row.
    placeholder_match_players = db.scalars(
        select(MatchPlayer).where(MatchPlayer.user_id == placeholder.id)
    ).all()
    for mp in placeholder_match_players:
        existing_mp = db.scalar(
            select(MatchPlayer).where(
                MatchPlayer.match_id == mp.match_id,
                MatchPlayer.user_id == real.id,
            )
        )
        if existing_mp:
            db.delete(mp)
        else:
            mp.user_id = real.id

    # Match creators (defensive — placeholders can't log in so this is rare).
    for m in db.scalars(select(Match).where(Match.created_by_id == placeholder.id)).all():
        m.created_by_id = real.id

    # Push the FK reassignments to the DB, then drop the placeholder's ORM
    # cache. Without this, the next db.delete(placeholder) would consult the
    # stale in-memory placeholder.match_players / .league_memberships
    # collections and try to "orphan" them by setting user_id = NULL — which
    # violates the NOT NULL constraint on those FK columns. Expiring forces
    # SQLAlchemy to lazy-load the (now empty) collections instead.
    db.flush()
    db.expire(placeholder)

    db.delete(placeholder)
    db.flush()
    return True


def memberships_for_home(db: Session, user_id: int) -> list[tuple[League, LeagueMember]]:
    memberships = db.scalars(
        select(LeagueMember)
        .where(
            LeagueMember.user_id == user_id,
            LeagueMember.status == LeagueMemberStatus.active,
        )
        .options(joinedload(LeagueMember.league))
    ).all()

    pairs = [(m.league, m) for m in memberships if m.league is not None]
    pairs.sort(
        key=lambda x: (
            int(not x[1].is_pinned),
            x[0].name.lower(),
        )
    )
    return pairs

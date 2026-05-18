from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import League, LeagueMember, LeagueMemberRole, LeagueMemberStatus, Match, Season


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

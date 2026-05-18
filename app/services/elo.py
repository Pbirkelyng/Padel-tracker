"""Doubles ELO — ratings stored on LeagueMember."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LeagueMember, Match


def _expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400))


def _team_rating(members: list[LeagueMember]) -> float:
    if not members:
        return 1000.0
    return sum(m.rating for m in members) / len(members)


def _league_members_for_team(db: Session, match: Match, team: str) -> list[LeagueMember]:
    user_ids = [mp.user_id for mp in match.players if mp.team == team]
    if not user_ids:
        return []
    return list(
        db.scalars(
            select(LeagueMember).where(
                LeagueMember.league_id == match.league_id,
                LeagueMember.user_id.in_(user_ids),
            )
        ).all()
    )


def compute_elo_delta(db: Session, match: Match, winner: str) -> float:
    settings = get_settings()
    k = settings.elo_k
    team_a = _league_members_for_team(db, match, "A")
    team_b = _league_members_for_team(db, match, "B")
    r_a = _team_rating(team_a)
    r_b = _team_rating(team_b)
    e_a = _expected_score(r_a, r_b)
    s_a = 1.0 if winner == "A" else 0.0
    return k * (s_a - e_a)


def apply_elo_for_match(db: Session, match: Match, winner: str) -> dict[int, float]:
    team_a = _league_members_for_team(db, match, "A")
    team_b = _league_members_for_team(db, match, "B")
    if len(team_a) != 2 or len(team_b) != 2:
        raise ValueError("Each team must have exactly 2 players for ELO")
    delta = compute_elo_delta(db, match, winner)
    deltas: dict[int, float] = {}
    for m in team_a:
        m.rating += delta
        deltas[m.user_id] = delta
    for m in team_b:
        m.rating -= delta
        deltas[m.user_id] = -delta
    db.flush()
    return deltas


def reverse_elo_for_match(db: Session, match: Match) -> None:
    if match.elo_delta is None:
        return
    delta = match.elo_delta
    for mp in match.players:
        if mp.team not in ("A", "B"):
            continue
        lm = db.scalar(
            select(LeagueMember).where(
                LeagueMember.league_id == match.league_id,
                LeagueMember.user_id == mp.user_id,
            )
        )
        if not lm:
            continue
        if mp.team == "A":
            lm.rating -= delta
        else:
            lm.rating += delta
    match.elo_delta = None
    match.winner_team = None
    db.flush()

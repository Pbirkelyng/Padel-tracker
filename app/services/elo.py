"""Doubles ELO — ratings stored on LeagueMember.

New formula (margin-aware):
    S_a   = 1.0 (win) | 0.0 (loss) | 0.5 (draw)
    E_a   = 1 / (1 + 10^((R_b - R_a) / 400))    standard expected score
    mult  = log(1 + |net_games|)                  margin multiplier
    delta = K * mult * (S_a - E_a)

net_games is the absolute total of (team_a_games - team_b_games) across all
sets, viewed from team A's side.  For a 6-0, 6-0 win by A: net = +12,
mult ≈ ln(13) ≈ 2.56.  For a 3-3 single set the multiplier is 0 and no
ratings change.
"""

import math

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


def margin_multiplier(game_diff: int) -> float:
    """log(1 + |game_diff|) — scales ELO change with the margin of victory."""
    return math.log(1 + abs(game_diff))


def _net_games_a(match: Match) -> int:
    """Net game difference from team A's perspective, across all set scores."""
    return sum(s.team_a_games - s.team_b_games for s in match.set_scores)


def compute_elo_delta(db: Session, match: Match, winner: str) -> float:
    """Compute the ELO delta for team A (positive = team A gains).

    winner must be 'A', 'B', or 'DRAW'.
    The delta is stored in match.elo_delta and later reversed if needed.
    """
    settings = get_settings()
    k = settings.elo_k
    team_a = _league_members_for_team(db, match, "A")
    team_b = _league_members_for_team(db, match, "B")
    r_a = _team_rating(team_a)
    r_b = _team_rating(team_b)
    e_a = _expected_score(r_a, r_b)

    if winner == "A":
        s_a = 1.0
    elif winner == "B":
        s_a = 0.0
    else:  # DRAW
        s_a = 0.5

    net = _net_games_a(match)
    mult = margin_multiplier(net)
    return k * mult * (s_a - e_a)


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

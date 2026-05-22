"""Leaderboard statistics per league and season."""

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import (
    LeagueMember,
    LeagueMemberStatus,
    Match,
    MatchPlayer,
    MatchStatus,
    Season,
    User,
    UserStatus,
)


@dataclass
class PlayerStats:
    user_id: int
    display_name: str
    email: str
    rating: float
    matches_played: int
    matches_won: int
    matches_lost: int
    sets_won: int
    sets_lost: int
    games_won: int
    games_lost: int

    @property
    def match_win_pct(self) -> float:
        if self.matches_played == 0:
            return 0.0
        return 100.0 * self.matches_won / self.matches_played

    @property
    def set_win_pct(self) -> float:
        total = self.sets_won + self.sets_lost
        if total == 0:
            return 0.0
        return 100.0 * self.sets_won / total


def compute_leaderboard(
    db: Session,
    league_id: int,
    season: Season,
) -> list[PlayerStats]:
    """Stats for active approved users in the league who played in this season."""
    settings = get_settings()
    default_r = settings.default_rating

    members = db.scalars(
        select(LeagueMember).where(
            LeagueMember.league_id == league_id,
            LeagueMember.status == LeagueMemberStatus.active,
        )
    ).all()

    rating_by_user: dict[int, float] = {}
    if season.is_current:
        for m in members:
            rating_by_user[m.user_id] = m.rating
    else:
        if season.final_ratings_json:
            try:
                raw = json.loads(season.final_ratings_json)
                rating_by_user = {int(k): float(v) for k, v in raw.items()}
            except (json.JSONDecodeError, ValueError, TypeError):
                rating_by_user = {}
        for m in members:
            rating_by_user.setdefault(m.user_id, default_r)

    users = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.status == UserStatus.approved).order_by(User.display_name)
        ).all()
    }

    stats_map: dict[int, PlayerStats] = {}
    for m in members:
        u = users.get(m.user_id)
        if not u:
            continue
        stats_map[u.id] = PlayerStats(
            user_id=u.id,
            display_name=u.display_name,
            email=u.email,
            rating=rating_by_user.get(u.id, default_r),
            matches_played=0,
            matches_won=0,
            matches_lost=0,
            sets_won=0,
            sets_lost=0,
            games_won=0,
            games_lost=0,
        )

    matches = db.scalars(
        select(Match)
        .where(
            Match.league_id == league_id,
            Match.season_id == season.id,
            Match.status == MatchStatus.completed,
        )
        .options(
            selectinload(Match.players).selectinload(MatchPlayer.user),
            selectinload(Match.set_scores),
        )
    ).all()

    for match in matches:
        if not match.set_scores:
            continue

        sets_a = sum(1 for s in match.set_scores if s.team_a_games > s.team_b_games)
        sets_b = sum(1 for s in match.set_scores if s.team_b_games > s.team_a_games)
        if sets_a > sets_b:
            match_winner: str | None = "A"
        elif sets_b > sets_a:
            match_winner = "B"
        else:
            match_winner = None  # draw

        for mp in match.players:
            if mp.team is None or mp.user_id not in stats_map:
                continue
            st = stats_map[mp.user_id]
            st.matches_played += 1
            if match_winner is not None:
                if mp.team == match_winner:
                    st.matches_won += 1
                else:
                    st.matches_lost += 1

            for s in match.set_scores:
                if mp.team == "A":
                    st.games_won += s.team_a_games
                    st.games_lost += s.team_b_games
                    if s.team_a_games > s.team_b_games:
                        st.sets_won += 1
                    else:
                        st.sets_lost += 1
                else:
                    st.games_won += s.team_b_games
                    st.games_lost += s.team_a_games
                    if s.team_b_games > s.team_a_games:
                        st.sets_won += 1
                    else:
                        st.sets_lost += 1

    return [s for s in stats_map.values() if s.matches_played > 0]


def sort_leaderboard(rows: list[PlayerStats], sort_by: str) -> list[PlayerStats]:
    key_map = {
        "rating": lambda r: r.rating,
        "name": lambda r: r.display_name.lower(),
        "matches": lambda r: r.match_win_pct,
        "sets": lambda r: r.set_win_pct,
        "games": lambda r: r.games_won - r.games_lost,
    }
    key_fn = key_map.get(sort_by, key_map["rating"])
    return sorted(rows, key=key_fn, reverse=True)

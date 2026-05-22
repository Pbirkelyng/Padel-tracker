"""Retroactive ELO recompute with margin-aware formula.

Revision ID: 006
Revises: 005
Create Date: 2026-05-22

Replays every completed match in every league/season (oldest first) with the
new formula:

    mult  = log(1 + |net_games_A|)
    delta = K * mult * (S_a - E_a)

Rewrites:
  - league_members.rating (current ratings)
  - matches.elo_delta
  - seasons.final_ratings_json (for ended seasons, re-snapshots after replay
    then re-applies the same soft-reset the app uses)

Self-contained — no imports from app/ so the migration stays stable.
"""

import json
import math
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ELO_K: float = float(os.environ.get("ELO_K", "24.0"))
DEFAULT_RATING: float = float(os.environ.get("DEFAULT_RATING", "1000.0"))


# ---------------------------------------------------------------------------
# Inline helpers (mirror app/services/elo.py without importing from app)
# ---------------------------------------------------------------------------

def _expected(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))


def _margin_mult(net_games: int) -> float:
    return math.log(1.0 + abs(net_games))


def _compute_delta(k: float, r_a: float, r_b: float, s_a: float, net_games: int) -> float:
    return k * _margin_mult(net_games) * (s_a - _expected(r_a, r_b))


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def upgrade() -> None:
    bind = op.get_bind()

    league_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM leagues ORDER BY id")).fetchall()]

    for league_id in league_ids:
        # 1. Reset all member ratings to default
        bind.execute(
            sa.text("UPDATE league_members SET rating = :d WHERE league_id = :lid"),
            {"d": DEFAULT_RATING, "lid": league_id},
        )

        # 2. Load seasons oldest-first
        seasons = bind.execute(
            sa.text(
                "SELECT id, is_current FROM seasons "
                "WHERE league_id = :lid ORDER BY id ASC"
            ),
            {"lid": league_id},
        ).fetchall()

        for season_id, is_current in seasons:
            # 3. Load completed matches in chronological order
            matches = bind.execute(
                sa.text(
                    "SELECT id, winner_team, ended_early "
                    "FROM matches "
                    "WHERE league_id = :lid AND season_id = :sid AND status = 'completed' "
                    "ORDER BY scheduled_at ASC, id ASC"
                ),
                {"lid": league_id, "sid": season_id},
            ).fetchall()

            for match_id, stored_winner, ended_early in matches:
                # 4. Reconstruct winner from set_scores (handles DRAW)
                set_rows = bind.execute(
                    sa.text(
                        "SELECT team_a_games, team_b_games "
                        "FROM set_scores WHERE match_id = :mid"
                    ),
                    {"mid": match_id},
                ).fetchall()

                if not set_rows:
                    continue

                sets_a = sum(1 for a, b in set_rows if a > b)
                sets_b = sum(1 for a, b in set_rows if b > a)
                net_games = sum(a - b for a, b in set_rows)

                if sets_a > sets_b:
                    winner = "A"
                    s_a = 1.0
                elif sets_b > sets_a:
                    winner = "B"
                    s_a = 0.0
                else:
                    winner = "DRAW"
                    s_a = 0.5

                # 5. Get team members and their current ratings
                players = bind.execute(
                    sa.text(
                        "SELECT mp.user_id, mp.team, lm.rating "
                        "FROM match_players mp "
                        "JOIN league_members lm "
                        "  ON lm.league_id = :lid AND lm.user_id = mp.user_id "
                        "WHERE mp.match_id = :mid AND mp.team IN ('A', 'B')"
                    ),
                    {"lid": league_id, "mid": match_id},
                ).fetchall()

                team_a = [(uid, r) for uid, team, r in players if team == "A"]
                team_b = [(uid, r) for uid, team, r in players if team == "B"]

                if len(team_a) != 2 or len(team_b) != 2:
                    # Can't compute ELO without exactly 2v2 — skip
                    bind.execute(
                        sa.text("UPDATE matches SET elo_delta = NULL WHERE id = :mid"),
                        {"mid": match_id},
                    )
                    continue

                r_a = sum(r for _, r in team_a) / 2.0
                r_b = sum(r for _, r in team_b) / 2.0

                delta = _compute_delta(ELO_K, r_a, r_b, s_a, net_games)

                # 6. Apply ratings
                for uid, _ in team_a:
                    bind.execute(
                        sa.text(
                            "UPDATE league_members SET rating = rating + :d "
                            "WHERE league_id = :lid AND user_id = :uid"
                        ),
                        {"d": delta, "lid": league_id, "uid": uid},
                    )
                for uid, _ in team_b:
                    bind.execute(
                        sa.text(
                            "UPDATE league_members SET rating = rating - :d "
                            "WHERE league_id = :lid AND user_id = :uid"
                        ),
                        {"d": delta, "lid": league_id, "uid": uid},
                    )

                # 7. Rewrite match metadata
                new_winner_team = None if winner == "DRAW" else winner
                bind.execute(
                    sa.text(
                        "UPDATE matches SET elo_delta = :d, winner_team = :w WHERE id = :mid"
                    ),
                    {"d": delta, "w": new_winner_team, "mid": match_id},
                )

            # 8. For ended seasons: snapshot final ratings, apply soft-reset
            if not is_current:
                member_rows = bind.execute(
                    sa.text(
                        "SELECT user_id, rating FROM league_members WHERE league_id = :lid"
                    ),
                    {"lid": league_id},
                ).fetchall()

                snapshot = {str(uid): r for uid, r in member_rows}
                bind.execute(
                    sa.text(
                        "UPDATE seasons SET final_ratings_json = :j WHERE id = :sid"
                    ),
                    {"j": json.dumps(snapshot), "sid": season_id},
                )

                # Soft-reset: same as end_current_season() in app
                for uid, r in member_rows:
                    new_r = (r + DEFAULT_RATING) / 2.0
                    bind.execute(
                        sa.text(
                            "UPDATE league_members SET rating = :r "
                            "WHERE league_id = :lid AND user_id = :uid"
                        ),
                        {"r": new_r, "lid": league_id, "uid": uid},
                    )


def downgrade() -> None:
    # Cannot restore prior elo_delta values — no-op
    pass

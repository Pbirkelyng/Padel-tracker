"""Padel set and match scoring validation."""

from dataclasses import dataclass
from math import ceil

VALID_SET_SCORES: set[tuple[int, int]] = {
    (6, 0),
    (6, 1),
    (6, 2),
    (6, 3),
    (6, 4),
    (7, 5),
    (7, 6),
}


@dataclass
class SetInput:
    set_number: int
    team_a_games: int
    team_b_games: int
    team_a_tb: int | None = None
    team_b_tb: int | None = None


@dataclass
class MatchResult:
    winner: str  # 'A' or 'B'
    sets_a: int
    sets_b: int


def _normalize_score(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a >= b else (b, a)


def validate_set_score(
    team_a_games: int,
    team_b_games: int,
    team_a_tb: int | None = None,
    team_b_tb: int | None = None,
) -> tuple[str, str | None]:
    """Validate a single set. Returns (winner, error_message)."""
    if team_a_games < 0 or team_b_games < 0:
        return "", "Games cannot be negative"
    if team_a_games == team_b_games:
        return "", "Set cannot be tied"

    norm = _normalize_score(team_a_games, team_b_games)
    if norm not in VALID_SET_SCORES:
        return "", f"Invalid set score {team_a_games}-{team_b_games}"

    winner = "A" if team_a_games > team_b_games else "B"

    # Tiebreak at 7-6
    if norm == (7, 6):
        if team_a_tb is not None or team_b_tb is not None:
            a_tb = team_a_tb or 0
            b_tb = team_b_tb or 0
            if a_tb < 0 or b_tb < 0:
                return "", "Tiebreak points cannot be negative"
            if a_tb == b_tb:
                return "", "Tiebreak cannot be tied"
            tb_winner = "A" if a_tb > b_tb else "B"
            if tb_winner != winner:
                return "", "Tiebreak winner must match set winner"
            tb_high = max(a_tb, b_tb)
            tb_low = min(a_tb, b_tb)
            if tb_high < 7:
                return "", "Tiebreak winner needs at least 7 points"
            if tb_high - tb_low < 2:
                return "", "Tiebreak must be won by 2 points"

    return winner, None


def sets_needed_to_win(best_of: int) -> int:
    return ceil(best_of / 2)


def validate_match_scores(
    sets: list[SetInput],
    best_of: int,
) -> tuple[MatchResult | None, str | None]:
    """Validate all sets for a match. Returns MatchResult or error."""
    if not sets:
        return None, "At least one set is required"

    needed = sets_needed_to_win(best_of)
    sets_a = 0
    sets_b = 0
    seen_numbers: set[int] = set()

    for s in sorted(sets, key=lambda x: x.set_number):
        if s.set_number in seen_numbers:
            return None, f"Duplicate set number {s.set_number}"
        seen_numbers.add(s.set_number)

        if sets_a >= needed or sets_b >= needed:
            return None, f"Set {s.set_number} played after match was already decided"

        winner, err = validate_set_score(
            s.team_a_games, s.team_b_games, s.team_a_tb, s.team_b_tb
        )
        if err:
            return None, f"Set {s.set_number}: {err}"

        if winner == "A":
            sets_a += 1
        else:
            sets_b += 1

    if sets_a < needed and sets_b < needed:
        return None, f"Match not complete — need {needed} sets to win (best of {best_of})"

    if sets_a >= needed and sets_b >= needed:
        return None, "Both teams cannot reach winning set count"

    winner = "A" if sets_a > sets_b else "B"
    return MatchResult(winner=winner, sets_a=sets_a, sets_b=sets_b), None


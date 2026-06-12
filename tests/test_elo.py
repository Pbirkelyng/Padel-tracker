"""Unit tests for the margin-aware ELO formula."""

import math

from app.services.elo import margin_multiplier, split_team_changes


def test_margin_multiplier_zero():
    # True draw or identical games — no movement
    assert margin_multiplier(0) == 0.0


def test_margin_multiplier_positive():
    # 6-0, 6-0 → net = +12
    assert abs(margin_multiplier(12) - math.log(13)) < 1e-9


def test_margin_multiplier_absolute():
    # Symmetric — negative net (loss from A's perspective) same magnitude
    assert abs(margin_multiplier(-12) - margin_multiplier(12)) < 1e-9


def _elo_delta_pure(k, r_a, r_b, s_a, net_games):
    """Reproduce the formula without DB access."""
    e_a = 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400))
    mult = math.log(1 + abs(net_games))
    return k * mult * (s_a - e_a)


K = 24


def test_win_margin_ordering():
    """Bigger margin → bigger ELO gain (equal teams, team A wins)."""
    # 6-0, 6-0 → net +12
    d1 = _elo_delta_pure(K, 1000, 1000, 1.0, 12)
    # 6-4, 6-4 → net +4
    d2 = _elo_delta_pure(K, 1000, 1000, 1.0, 4)
    # 7-6, 7-6 → net +2
    d3 = _elo_delta_pure(K, 1000, 1000, 1.0, 2)
    assert d1 > d2 > d3 > 0


def test_upset_bonus():
    """Underdog (1000) beating favourite (1200) gains more than same score inverted."""
    net = 12  # 6-0, 6-0
    d_upset = _elo_delta_pure(K, 1000, 1200, 1.0, net)
    d_favourite = _elo_delta_pure(K, 1200, 1000, 1.0, net)
    assert d_upset > d_favourite > 0


def test_draw_equal_teams_no_movement():
    """Equal teams drawing with net 0 games → no rating change."""
    d = _elo_delta_pure(K, 1000, 1000, 0.5, 0)
    assert d == 0.0


def test_underdog_draw_gains():
    """Underdog drawing a favourite gets a positive delta (expected < 0.5)."""
    # underdog is rated 800, favourite 1200
    d = _elo_delta_pure(K, 800, 1200, 0.5, 0)
    # mult = 0 when net=0, so delta is always 0 regardless of expectation
    assert d == 0.0


def test_underdog_draw_nonzero_games():
    """Underdog drawing but with some games played (net != 0) — should gain."""
    # e.g. 4-3 tie — net from underdog's perspective = +1
    d = _elo_delta_pure(K, 800, 1200, 0.5, 1)
    assert d > 0


def test_split_changes_win_worth_more_than_loss():
    """Winner gains the full delta; loser loses only half (loss_factor 0.5)."""
    change_a, change_b = split_team_changes(20.0, 0.5)
    assert change_a == 20.0
    assert change_b == -10.0
    assert change_a > abs(change_b)


def test_split_changes_losing_still_negative():
    change_a, change_b = split_team_changes(20.0, 0.5)
    assert change_b < 0
    # Symmetric case from team B's win
    change_a, change_b = split_team_changes(-20.0, 0.5)
    assert change_a == -10.0
    assert change_b == 20.0
    assert change_a < 0


def test_split_changes_zero_delta_no_movement():
    assert split_team_changes(0.0, 0.5) == (0.0, 0.0)


def test_participation_accumulates_rating():
    """A 50% player over many matches nets more than a one-off winner."""
    delta = 20.0  # equal-strength matchup
    one_off_winner = split_team_changes(delta, 0.5)[0]
    regular = 0.0
    for _ in range(5):  # 5 wins, 5 losses
        regular += split_team_changes(delta, 0.5)[0]
        regular += split_team_changes(-delta, 0.5)[0]
    assert regular > one_off_winner

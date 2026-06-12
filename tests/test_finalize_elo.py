"""Regression tests for ELO application during match finalize."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    Match,
    MatchPlayer,
    MatchStatus,
    Season,
    SetScore,
    User,
    UserStatus,
)
from app.services.elo import apply_elo_for_match, compute_elo_delta, split_team_changes


def _make_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        password_hash="hash",
        display_name=email.split("@")[0],
        status=UserStatus.approved,
    )
    db.add(user)
    db.flush()
    return user


def _make_league_with_match(db: Session) -> tuple[Match, list[LeagueMember]]:
    creator = _make_user(db, "creator@example.com")
    players = [_make_user(db, f"player{i}@example.com") for i in range(1, 5)]

    league = League(
        name="Test League",
        slug="test-league",
        created_by_id=creator.id,
    )
    db.add(league)
    db.flush()

    season = Season(league_id=league.id, name="Season 1", is_current=True)
    db.add(season)
    db.flush()

    members: list[LeagueMember] = []
    for user in players:
        member = LeagueMember(
            league_id=league.id,
            user_id=user.id,
            role=LeagueMemberRole.member,
            status=LeagueMemberStatus.active,
            rating=1000.0,
        )
        db.add(member)
        members.append(member)
    db.flush()

    match = Match(
        scheduled_at=datetime(2026, 6, 4, 18, 0),
        best_of=3,
        status=MatchStatus.scheduled,
        league_id=league.id,
        season_id=season.id,
        created_by_id=creator.id,
    )
    db.add(match)
    db.flush()

    teams = ["A", "A", "B", "B"]
    for user, team in zip(players, teams, strict=True):
        db.add(MatchPlayer(match_id=match.id, user_id=user.id, team=team))
    db.flush()

    return match, members


def _load_match_like_finalize(db: Session, match_id: int) -> Match:
    return db.scalars(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.players),
            selectinload(Match.set_scores),
        )
    ).first()


def _insert_set_scores_like_finalize(db: Session, match: Match) -> int:
    """Mirror save_scores finalize: FK-only inserts leave set_scores stale."""
    for existing in list(match.set_scores):
        db.delete(existing)
    db.flush()

    sets = [
        (1, 7, 6, 7, 3),
        (2, 3, 6, None, None),
        (3, 6, 0, None, None),
    ]
    for set_number, a_games, b_games, a_tb, b_tb in sets:
        db.add(
            SetScore(
                match_id=match.id,
                set_number=set_number,
                team_a_games=a_games,
                team_b_games=b_games,
                team_a_tb=a_tb,
                team_b_tb=b_tb,
            )
        )
    db.flush()
    return sum(a_games - b_games for _, a_games, b_games, _, _ in sets)


def test_finalize_path_without_net_games_reads_stale_collection(db_session: Session):
    """Demonstrate the stale-collection bug when net_games is omitted."""
    match, _ = _make_league_with_match(db_session)
    loaded = _load_match_like_finalize(db_session, match.id)
    net = _insert_set_scores_like_finalize(db_session, loaded)

    assert net == 4
    assert loaded.set_scores == []

    delta = compute_elo_delta(db_session, loaded, "A")
    assert delta == 0.0


def test_finalize_applies_nonzero_elo_with_net_games(db_session: Session):
    """3-set win (7-6, 3-6, 6-0) must move ratings when net_games is passed."""
    match, members = _make_league_with_match(db_session)
    ratings_before = [member.rating for member in members]

    loaded = _load_match_like_finalize(db_session, match.id)
    net = _insert_set_scores_like_finalize(db_session, loaded)

    delta = compute_elo_delta(db_session, loaded, "A", net_games=net)
    assert delta != 0.0

    apply_elo_for_match(db_session, loaded, "A", net_games=net)
    db_session.flush()

    change_a, change_b = split_team_changes(delta)
    ratings_after = [member.rating for member in members]
    assert ratings_after != ratings_before
    assert ratings_after[0] == ratings_before[0] + change_a
    assert ratings_after[1] == ratings_before[1] + change_a
    assert ratings_after[2] == ratings_before[2] + change_b
    assert ratings_after[3] == ratings_before[3] + change_b
    # Winners gain more than losers lose
    assert change_a > 0
    assert change_b < 0
    assert change_a > abs(change_b)

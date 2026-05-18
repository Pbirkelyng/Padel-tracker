import pytest

from app.services.scoring import SetInput, validate_match_scores, validate_set_score


@pytest.mark.parametrize(
    "a,b",
    [(6, 0), (6, 4), (7, 5), (7, 6)],
)
def test_valid_sets(a, b):
    winner, err = validate_set_score(a, b)
    assert err is None
    assert winner == "A"


def test_invalid_set():
    _, err = validate_set_score(5, 5)
    assert err is not None


def test_match_best_of_3():
    sets = [
        SetInput(1, 6, 2),
        SetInput(2, 6, 3),
    ]
    result, err = validate_match_scores(sets, 3)
    assert err is None
    assert result.winner == "A"
    assert result.sets_a == 2


def test_match_incomplete():
    sets = [SetInput(1, 6, 4)]
    result, err = validate_match_scores(sets, 3)
    assert result is None
    assert err is not None

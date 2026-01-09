import pytest

from src.models.stats import MoveStats


def test_advantage_padding_shrinks_toward_balanced():
    stats = MoveStats(
        uci="e2e4",
        san="e4",
        white_wins=8,
        draws=1,
        black_wins=1,
        total_games=10,
    )

    advantage = stats.advantage(
        for_white=True,
        min_games_threshold=50,
        padding_strength=90,
    )

    # weight = 10 / (10 + 90) = 0.1; 0.1 * 0.7 = 0.07
    assert pytest.approx(0.07) == advantage


def test_advantage_padding_skips_when_sample_is_large():
    stats = MoveStats(
        uci="d2d4",
        san="d4",
        white_wins=60,
        draws=20,
        black_wins=20,
        total_games=100,
    )

    advantage = stats.advantage(
        for_white=True,
        min_games_threshold=50,
        padding_strength=90,
    )

    # Raw advantage is 0.6 - 0.2 = 0.4; no padding when total_games >= threshold.
    assert pytest.approx(0.4) == advantage

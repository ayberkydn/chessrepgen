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
        padding_strength=90,
    )

    # weight = 10 / (10 + 90) = 0.1; 0.1 * 0.7 = 0.07
    assert pytest.approx(0.07) == advantage


def test_advantage_padding_applied_to_all_samples():
    """Verify padding is applied regardless of sample size."""
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
        padding_strength=100,
    )

    # Raw advantage is 0.6 - 0.2 = 0.4
    # weight = 100 / (100 + 100) = 0.5; 0.5 * 0.4 = 0.2
    assert pytest.approx(0.2) == advantage


def test_advantage_no_padding_when_zero():
    """Verify no padding is applied when padding_strength is 0."""
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
        padding_strength=0,
    )

    # Raw advantage is 0.6 - 0.2 = 0.4; no padding when padding_strength is 0
    assert pytest.approx(0.4) == advantage

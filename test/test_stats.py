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


def test_calculate_padding_ratio_only():
    """Test padding calculation with ratio-based padding only."""
    from src.services.stats import calculate_padding

    # 1000 games * 0.1 = 100 padding
    assert calculate_padding(1000, 0.1, 0) == 100

    # 500 games * 0.05 = 25 padding
    assert calculate_padding(500, 0.05, 0) == 25


def test_calculate_padding_static_only():
    """Test padding calculation with static padding only."""
    from src.services.stats import calculate_padding

    # Static 50 games, no ratio
    assert calculate_padding(1000, 0.0, 50) == 50

    # Static 100 games, no ratio
    assert calculate_padding(0, 0.0, 100) == 100


def test_calculate_padding_combined():
    """Test padding calculation with both ratio and static padding."""
    from src.services.stats import calculate_padding

    # 1000 * 0.1 + 50 = 150
    assert calculate_padding(1000, 0.1, 50) == 150

    # 500 * 0.02 + 100 = 110
    assert calculate_padding(500, 0.02, 100) == 110


def test_calculate_padding_zero_parent_games():
    """Test padding calculation when parent has zero games."""
    from src.services.stats import calculate_padding

    # No parent games, only static padding applies
    assert calculate_padding(0, 0.1, 50) == 50
    assert calculate_padding(0, 0.1, 0) == 0

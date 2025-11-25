import pytest

from src.config import Config


def test_validate_normalizes_advantage_aggregation():
    config = Config(advantage_aggregation="Mean")

    config.validate()

    assert config.advantage_aggregation == "mean"


def test_validate_rejects_unknown_time_control():
    config = Config(time_control=["rapid", "hyper"])

    with pytest.raises(ValueError):
        config.validate()


def test_validate_rejects_negative_postprune_thresholds():
    with pytest.raises(ValueError):
        Config(postprune_min_games=-1).validate()

    with pytest.raises(ValueError):
        Config(postprune_max_depth=-2).validate()

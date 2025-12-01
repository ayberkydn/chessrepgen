import pytest

from src.config import Config, PostprocessConfig


def test_validate_normalizes_advantage_aggregation():
    config = Config(advantage_aggregation="Mean")

    config.validate()

    assert config.advantage_aggregation == "mean"


def test_validate_rejects_unknown_time_control():
    config = Config(time_control=["rapid", "hyper"])

    with pytest.raises(ValueError):
        config.validate()


def test_postprocess_config_splits_comma_delimited_initial_moves():
    config = PostprocessConfig(
        initial_lines="e4 e6, d4 d5", input_file="in.pgn", output_file="out.pgn"
    )

    config.validate()

    assert config.initial_lines == ["e4 e6", "d4 d5"]

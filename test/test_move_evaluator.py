from src.config import Config
from src.evaluator import MoveEvaluator


def test_player_move_selection_filters_by_reference_and_tolerance():
    config = Config()
    config.min_highrating_popularity = 0.2
    config.min_highrating_games = 100
    config.advantage_tolerance = 0.05
    evaluator = MoveEvaluator(config, side="white")

    lichess_stats = {
        "moves": [
            {"uci": "e2e4", "san": "e4", "white": 60, "draws": 20, "black": 20},
            {"uci": "d2d4", "san": "d4", "white": 45, "draws": 25, "black": 30},
            {"uci": "c2c4", "san": "c4", "white": 30, "draws": 20, "black": 50},
        ]
    }

    reference_stats = {
        "white": 300,
        "draws": 100,
        "black": 100,
        "moves": [
            {"uci": "e2e4", "white": 200, "draws": 100, "black": 50},
            {"uci": "d2d4", "white": 60, "draws": 20, "black": 20},
            {"uci": "c2c4", "white": 25, "draws": 15, "black": 10},
        ],
    }

    moves = evaluator.evaluate_position(
        lichess_stats, reference_stats, is_player_turn=True, depth=0
    )

    assert [m.uci for m in moves] == ["e2e4"]


def test_opponent_fallback_returns_top_moves_when_threshold_unmet():
    config = Config()
    config.min_opponent_popularity = 0.7
    config.opponent_fallback_count = 2
    evaluator = MoveEvaluator(config, side="white")

    lichess_stats = {
        "moves": [
            {"uci": "e2e4", "san": "e4", "white": 20, "draws": 10, "black": 20},
            {"uci": "d2d4", "san": "d4", "white": 12, "draws": 8, "black": 10},
            {"uci": "c2c4", "san": "c4", "white": 7, "draws": 3, "black": 10},
        ]
    }

    moves = evaluator.evaluate_position(
        lichess_stats, player_reference_stats=None, is_player_turn=False, depth=0
    )

    assert [m.total_games for m in moves] == [50, 30]

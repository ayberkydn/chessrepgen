from src.config import Config
from src.services.evaluator import MoveEvaluator


def test_player_move_selection_filters_by_advantage_tolerance():
    config = Config()
    config.advantage_tolerance = 0.05
    evaluator = MoveEvaluator(config, side="white")

    lichess_stats = {
        "moves": [
            {
                "uci": "e2e4",
                "san": "e4",
                "white": 60,
                "draws": 20,
                "black": 20,
            },  # advantage: 0.4
            {
                "uci": "d2d4",
                "san": "d4",
                "white": 45,
                "draws": 25,
                "black": 30,
            },  # advantage: 0.15
            {
                "uci": "c2c4",
                "san": "c4",
                "white": 30,
                "draws": 20,
                "black": 50,
            },  # advantage: -0.15
        ]
    }

    moves = evaluator.evaluate_position(
        lichess_stats, None, is_player_turn=True, depth=0
    )

    # Only e4 (0.4) should be within tolerance (0.05) of best advantage
    # d4 (0.15) is 0.25 away from 0.4, which exceeds 0.05 tolerance
    assert [m.uci for m in moves] == ["e2e4"]


def test_player_move_selection_filters_by_popularity():
    config = Config()
    config.advantage_tolerance = 1.0  # Allow all moves by advantage
    config.min_player_popularity = 0.3
    evaluator = MoveEvaluator(config, side="white")

    lichess_stats = {
        "moves": [
            {
                "uci": "e2e4",
                "san": "e4",
                "white": 60,
                "draws": 20,
                "black": 20,
            },  # 100 games, 50%
            {
                "uci": "d2d4",
                "san": "d4",
                "white": 45,
                "draws": 25,
                "black": 30,
            },  # 100 games, 50%
            {
                "uci": "c2c4",
                "san": "c4",
                "white": 0,
                "draws": 0,
                "black": 1,
            },  # 1 game, ~0.5%
        ]
    }

    moves = evaluator.evaluate_position(
        lichess_stats, None, is_player_turn=True, depth=0
    )

    # c2c4 should be filtered out because popularity is too low
    assert [m.uci for m in moves] == ["e2e4", "d2d4"]


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

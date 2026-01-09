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


def test_player_padding_influences_move_selection():
    config = Config()
    config.advantage_tolerance = 0.005  # Tighter tolerance to exclude a3
    config.min_player_popularity = 0.0
    config.padding_ratio = 0.02
    evaluator = MoveEvaluator(config, side="white")

    # Parent position has 100 games, so padding = 100 * 0.02 = 2
    lichess_stats = {
        "white": 50,
        "draws": 0,
        "black": 50,
        "moves": [
            {
                "uci": "a2a3",
                "san": "a3",
                "white": 6,
                "draws": 0,
                "black": 4,
            },  # 10 games, raw advantage: 0.2, weight = 10/(10+2) = 0.833, padded = 0.167
            {
                "uci": "e2e4",
                "san": "e4",
                "white": 59,
                "draws": 0,
                "black": 41,
            },  # 100 games, raw advantage: 0.18, weight = 100/(100+2) = 0.98, padded = 0.176
        ],
    }

    moves = evaluator.evaluate_position(
        lichess_stats, None, is_player_turn=True, depth=0
    )

    # e4 has higher padded advantage (0.176 > 0.167), so it comes first
    # a3 is excluded because its padded advantage (0.167) is ~0.0098 below e4's (0.176),
    # which exceeds the 0.005 tolerance
    assert [m.uci for m in moves] == ["e2e4"]

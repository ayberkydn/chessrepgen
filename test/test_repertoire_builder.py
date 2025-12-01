import chess
import pytest

from src.config import Config
from src.models.graph import RepertoireEdge, RepertoireNode
from src.models.stats import MoveStats
from src.services.pruner import RepertoirePruner
from src.services.repertoire_builder import RepertoireBuilder
from src.services.stats import calculate_moves_weighted_advantage, merge_reference_stats


def make_builder(side: str = "white") -> RepertoireBuilder:
    builder = RepertoireBuilder.__new__(RepertoireBuilder)
    builder.config = Config()
    builder.is_white = side == "white"
    builder.pruner = RepertoirePruner(builder.config, builder.is_white)
    return builder


def test_merge_reference_stats_combines_counts_and_ratings():
    master_stats = {
        "white": 10,
        "draws": 5,
        "black": 8,
        "moves": [
            {
                "uci": "e2e4",
                "san": "e4",
                "white": 3,
                "draws": 1,
                "black": 2,
                "averageRating": 2300,
                "opening": "King's Pawn",
            },
            {"uci": "d2d4", "san": "d4", "white": 2, "draws": 1, "black": 1},
        ],
    }

    highrating_stats = {
        "white": 5,
        "draws": 6,
        "black": 4,
        "moves": [
            {
                "uci": "e2e4",
                "san": "e4",
                "white": 4,
                "draws": 2,
                "black": 4,
                "averageRating": 2100,
            },
            {
                "uci": "c2c4",
                "san": "c4",
                "white": 1,
                "draws": 1,
                "black": 2,
                "averageRating": 2200,
            },
        ],
    }

    merged = merge_reference_stats(master_stats, highrating_stats)

    assert merged["white"] == 15
    assert merged["draws"] == 11
    assert merged["black"] == 12

    e4_entry = next(move for move in merged["moves"] if move["uci"] == "e2e4")
    assert e4_entry["white"] == 7
    assert e4_entry["draws"] == 3
    assert e4_entry["black"] == 6
    assert pytest.approx(2175.0, rel=1e-4) == e4_entry["averageRating"]
    assert merged["moves"][0]["uci"] == "e2e4"


def test_calculate_moves_weighted_advantage_respects_aggregation():
    moves = [
        {"uci": "m1", "white": 32, "draws": 0, "black": 8},  # advantage 0.6, weight 40
        {"uci": "m2", "white": 21, "draws": 7, "black": 7},  # advantage 0.4, weight 35
        {"uci": "m3", "white": 5, "draws": 5, "black": 15},  # advantage -0.4, weight 25
    ]

    median_advantage = calculate_moves_weighted_advantage(
        moves, is_white=True, aggregation_method="median"
    )
    assert pytest.approx(0.4) == median_advantage

    mean_advantage = calculate_moves_weighted_advantage(
        moves, is_white=True, aggregation_method="mean"
    )
    assert pytest.approx(0.28) == mean_advantage


def test_compute_terminal_advantage_prefers_player_best_and_opponent_average():
    builder = make_builder()

    player_board = chess.Board()
    player_node = RepertoireNode(
        board=player_board.copy(),
        fen=player_board.fen(),
        key="player-root",
        is_player_turn=True,
    )

    player_best = MoveStats("e2e4", "e4", 15, 0, 5, 20)  # advantage 0.5
    player_second = MoveStats("d2d4", "d4", 12, 0, 8, 20)  # advantage 0.2

    player_node.edges = [
        RepertoireEdge(
            parent=player_node,
            child=None,
            move=chess.Move.from_uci("e2e4"),
            move_san="e4",
            stats=player_best,
            resulting_depth=1,
            comment="",
            termination_reason=None,
            is_terminal=True,
        ),
        RepertoireEdge(
            parent=player_node,
            child=None,
            move=chess.Move.from_uci("d2d4"),
            move_san="d4",
            stats=player_second,
            resulting_depth=1,
            comment="",
            termination_reason=None,
            is_terminal=True,
        ),
    ]

    player_value = builder.pruner._compute_terminal_advantage(player_node, {})
    assert pytest.approx(0.5) == player_value
    assert pytest.approx(0.5) == player_node.terminal_advantage

    opponent_board = chess.Board()
    opponent_node = RepertoireNode(
        board=opponent_board.copy(),
        fen=opponent_board.fen(),
        key="opponent-root",
        is_player_turn=False,
    )

    opponent_main = MoveStats("e7e5", "e5", 18, 3, 9, 30)  # advantage 0.3
    opponent_risky = MoveStats("c7c5", "c5", 4, 1, 5, 10)  # advantage -0.1

    opponent_node.edges = [
        RepertoireEdge(
            parent=opponent_node,
            child=None,
            move=chess.Move.from_uci("e7e5"),
            move_san="e5",
            stats=opponent_main,
            resulting_depth=1,
            comment="",
            termination_reason=None,
            is_terminal=True,
        ),
        RepertoireEdge(
            parent=opponent_node,
            child=None,
            move=chess.Move.from_uci("c7c5"),
            move_san="c5",
            stats=opponent_risky,
            resulting_depth=1,
            comment="",
            termination_reason=None,
            is_terminal=True,
        ),
    ]

    opponent_value = builder.pruner._compute_terminal_advantage(opponent_node, {})
    assert pytest.approx(0.2) == opponent_value
    assert pytest.approx(0.2) == opponent_node.terminal_advantage

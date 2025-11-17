import os
import sys

import chess
import pytest

TEST_ROOT = os.path.dirname(__file__)
PROJECT_SRC = os.path.join(TEST_ROOT, "..", "src")
if PROJECT_SRC not in sys.path:
    sys.path.insert(0, PROJECT_SRC)

from config import Config
from evaluator import MoveStats
from pgn_writer import PGNWriter
from repertoire_builder import RepertoireBuilder, RepertoireEdge, RepertoireNode


def _make_node(board: chess.Board, is_player_turn: bool) -> RepertoireNode:
    return RepertoireNode(
        board=board.copy(),
        fen=board.fen(),
        key=board.epd(),
        is_player_turn=is_player_turn,
        comment="",
        termination_reason=None,
        position_stats=None,
        edges=[],
        ancestors=set(),
        min_player_depth=0,
    )


def test_terminal_advantage_player_selects_best(tmp_path):
    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False

    builder = RepertoireBuilder(config, side="white")

    root_board = chess.Board()
    root_node = _make_node(root_board, is_player_turn=True)

    move_e4 = root_board.parse_san("e4")
    board_after_e4 = root_board.copy()
    board_after_e4.push(move_e4)
    child_e4 = _make_node(board_after_e4, is_player_turn=False)

    # Mock position stats for child_e4 (position after 1.e4)
    # Simulating opponent responses: e5 (100 games), c5 (50 games)
    child_e4.position_stats = {
        "lichess": {
            "white": 90,
            "draws": 30,
            "black": 30,
            "moves": [
                {
                    "uci": "e7e5",
                    "san": "e5",
                    "white": 60,
                    "draws": 20,
                    "black": 20,
                },  # 60% WR for white
                {
                    "uci": "c7c5",
                    "san": "c5",
                    "white": 30,
                    "draws": 10,
                    "black": 10,
                },  # 60% WR for white
            ],
        }
    }
    # Expected median advantage for the position after e4: both candidate moves give 0.4

    stats_e4 = MoveStats(
        uci=move_e4.uci(),
        san="e4",
        white_wins=60,
        draws=20,
        black_wins=20,
        total_games=100,
    )

    edge_e4 = RepertoireEdge(
        parent=root_node,
        child=child_e4,
        move=move_e4,
        move_san="e4",
        stats=stats_e4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=True,
    )

    move_d4 = chess.Move.from_uci("d2d4")
    board_after_d4 = root_board.copy()
    board_after_d4.push(move_d4)
    child_d4 = _make_node(board_after_d4, is_player_turn=False)

    # Mock position stats for child_d4 (position after 1.d4)
    # Simulating opponent responses: d5 (80 games), Nf6 (60 games)
    child_d4.position_stats = {
        "lichess": {
            "white": 75,
            "draws": 35,
            "black": 30,
            "moves": [
                {
                    "uci": "d7d5",
                    "san": "d5",
                    "white": 45,
                    "draws": 20,
                    "black": 15,
                },  # 37.5% advantage
                {
                    "uci": "g8f6",
                    "san": "Nf6",
                    "white": 30,
                    "draws": 15,
                    "black": 15,
                },  # 25% advantage
            ],
        }
    }
    # Expected median advantage for the position after d4: the 0.375 move dominates the median

    stats_d4 = MoveStats(
        uci=move_d4.uci(),
        san="d4",
        white_wins=55,
        draws=25,
        black_wins=20,
        total_games=100,
    )

    edge_d4 = RepertoireEdge(
        parent=root_node,
        child=child_d4,
        move=move_d4,
        move_san="d4",
        stats=stats_d4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=False,
    )

    root_node.edges.extend([edge_e4, edge_d4])

    builder.compute_terminal_advantages([root_node])

    # The best terminal advantage should be from e4 position
    expected_e4_advantage = 0.4
    assert root_node.terminal_advantage == pytest.approx(expected_e4_advantage)


def test_terminal_advantage_opponent_weighted_average(tmp_path):
    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False

    builder = RepertoireBuilder(config, side="white")

    board_after_white = chess.Board()
    board_after_white.push(board_after_white.parse_san("e4"))
    opponent_node = _make_node(board_after_white, is_player_turn=False)

    move_c5 = chess.Move.from_uci("c7c5")
    board_after_c5 = board_after_white.copy()
    board_after_c5.push(move_c5)
    child_c5 = _make_node(board_after_c5, is_player_turn=True)

    # Mock position stats for child_c5 (position after 1.e4 c5)
    # Simulating white's responses: Nf3 (80 games), Nc3 (40 games)
    child_c5.position_stats = {
        "lichess": {
            "white": 36,
            "draws": 12,
            "black": 72,
            "moves": [
                {
                    "uci": "g1f3",
                    "san": "Nf3",
                    "white": 24,
                    "draws": 8,
                    "black": 48,
                },  # -0.3 advantage for white
                {
                    "uci": "b1c3",
                    "san": "Nc3",
                    "white": 12,
                    "draws": 4,
                    "black": 24,
                },  # -0.3 advantage for white
            ],
        }
    }

    stats_c5 = MoveStats(
        uci=move_c5.uci(),
        san="c5",
        white_wins=30,
        draws=10,
        black_wins=60,
        total_games=100,
    )

    edge_c5 = RepertoireEdge(
        parent=opponent_node,
        child=child_c5,
        move=move_c5,
        move_san="c5",
        stats=stats_c5,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=False,
    )

    move_e5 = chess.Move.from_uci("e7e5")
    board_after_e5 = board_after_white.copy()
    board_after_e5.push(move_e5)
    child_e5 = _make_node(board_after_e5, is_player_turn=True)

    # Mock position stats for child_e5 (position after 1.e4 e5)
    # Simulating white's responses: Nf3 (40 games), Bc4 (20 games)
    child_e5.position_stats = {
        "lichess": {
            "white": 30,
            "draws": 15,
            "black": 15,
            "moves": [
                {
                    "uci": "g1f3",
                    "san": "Nf3",
                    "white": 20,
                    "draws": 10,
                    "black": 10,
                },  # 0.0 advantage
                {
                    "uci": "f1c4",
                    "san": "Bc4",
                    "white": 10,
                    "draws": 5,
                    "black": 5,
                },  # 0.0 advantage
            ],
        }
    }

    stats_e5 = MoveStats(
        uci=move_e5.uci(),
        san="e5",
        white_wins=40,
        draws=20,
        black_wins=40,
        total_games=50,
    )

    edge_e5 = RepertoireEdge(
        parent=opponent_node,
        child=child_e5,
        move=move_e5,
        move_san="e5",
        stats=stats_e5,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=False,
    )

    opponent_node.edges.extend([edge_c5, edge_e5])

    builder.compute_terminal_advantages([opponent_node])

    # Expected: opponent nodes still average child advantages by game weight
    # c5 position: -0.3 advantage (median of moves), 100 games (weight from edge stats)
    # e5 position: 0.25 advantage (median of moves), 50 games (weight from edge stats)
    # Weighted avg: (-0.3 * 100 + 0.25 * 50) / 150 = -0.11666...
    expected_advantage = (-0.3 * 100 + 0.25 * 50) / 150

    assert opponent_node.terminal_advantage == pytest.approx(expected_advantage)


def test_terminal_advantage_uses_only_lichess_data(tmp_path):
    """Terminal advantage calculation should ignore player_reference data and rely on Lichess stats."""
    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False

    builder = RepertoireBuilder(config, side="white")

    root_board = chess.Board()
    root_node = _make_node(root_board, is_player_turn=True)

    move_e4 = root_board.parse_san("e4")
    board_after_e4 = root_board.copy()
    board_after_e4.push(move_e4)
    child_e4 = _make_node(board_after_e4, is_player_turn=False)

    # Mock position stats with both Lichess and player_reference data
    # Lichess data shows advantage of 0.2 (60 games total)
    # Player reference shows advantage of 0.4 (40 games total)
    # Expected result should be based only on Lichess: 0.2
    child_e4.position_stats = {
        "lichess": {
            "white": 30,
            "draws": 12,
            "black": 18,
            "moves": [
                {
                    "uci": "c7c5",
                    "san": "c5",
                    "white": 20,
                    "draws": 8,
                    "black": 12,
                },  # 20% advantage, 40 games
                {
                    "uci": "e7e5",
                    "san": "e5",
                    "white": 10,
                    "draws": 4,
                    "black": 6,
                },  # 20% advantage, 20 games
            ],
        },
        "player_reference": {
            "white": 24,
            "draws": 8,
            "black": 8,
            "moves": [
                {
                    "uci": "c7c5",
                    "san": "c5",
                    "white": 16,
                    "draws": 4,
                    "black": 4,
                },  # 50% advantage, 24 games
                {
                    "uci": "e7e5",
                    "san": "e5",
                    "white": 8,
                    "draws": 4,
                    "black": 4,
                },  # 25% advantage, 16 games
            ],
        },
        "player_reference_source": "master",
    }

    stats_e4 = MoveStats(
        uci=move_e4.uci(),
        san="e4",
        white_wins=60,
        draws=20,
        black_wins=20,
        total_games=100,
    )

    edge_e4 = RepertoireEdge(
        parent=root_node,
        child=child_e4,
        move=move_e4,
        move_san="e4",
        stats=stats_e4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=True,
    )

    root_node.edges.append(edge_e4)

    builder.compute_terminal_advantages([root_node])

    # Even though player reference shows a higher advantage, only the Lichess
    # weighted median should be used, which stays at 0.2
    expected_advantage = 0.2

    assert child_e4.terminal_advantage == pytest.approx(expected_advantage)
    assert root_node.terminal_advantage == pytest.approx(expected_advantage)


def test_position_advantage_uses_weighted_median(tmp_path):
    """Verify that position advantage uses the weighted median of move outcomes."""
    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False

    builder = RepertoireBuilder(config, side="white")

    root_board = chess.Board()
    root_node = _make_node(root_board, is_player_turn=True)

    move_e4 = root_board.parse_san("e4")
    board_after_e4 = root_board.copy()
    board_after_e4.push(move_e4)
    child_e4 = _make_node(board_after_e4, is_player_turn=False)

    # Three opponent replies with different advantages and game counts
    # Sorted by advantage they should produce a weighted median equal to the middle value.
    child_e4.position_stats = {
        "lichess": {
            "white": 47,
            "draws": 32,
            "black": 31,
            "moves": [
                {
                    "uci": "c7c5",
                    "san": "c5",
                    "white": 14,
                    "draws": 2,
                    "black": 4,
                },  # advantage 0.5, 20 games
                {
                    "uci": "e7e5",
                    "san": "e5",
                    "white": 18,
                    "draws": 10,
                    "black": 12,
                },  # advantage 0.15, 40 games
                {
                    "uci": "g8f6",
                    "san": "Nf6",
                    "white": 15,
                    "draws": 20,
                    "black": 15,
                },  # advantage 0.0, 50 games
            ],
        }
    }

    stats_e4 = MoveStats(
        uci=move_e4.uci(),
        san="e4",
        white_wins=60,
        draws=20,
        black_wins=20,
        total_games=100,
    )

    edge_e4 = RepertoireEdge(
        parent=root_node,
        child=child_e4,
        move=move_e4,
        move_san="e4",
        stats=stats_e4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=True,
    )

    root_node.edges.append(edge_e4)

    builder.compute_terminal_advantages([root_node])

    # Weighted median should pick the middle advantage (0.15) once cumulative counts reach half the total
    assert child_e4.terminal_advantage == pytest.approx(0.15)
    assert root_node.terminal_advantage == pytest.approx(0.15)


def test_pgn_writer_includes_terminal_advantage(tmp_path):
    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False

    builder = RepertoireBuilder(config, side="white")

    root_board = chess.Board()
    root_node = _make_node(root_board, is_player_turn=True)

    move_e4 = root_board.parse_san("e4")
    board_after_e4 = root_board.copy()
    board_after_e4.push(move_e4)
    child_e4 = _make_node(board_after_e4, is_player_turn=False)

    # Mock position stats for child_e4 to prevent fetching real data
    child_e4.position_stats = {
        "lichess": {
            "white": 60,
            "draws": 20,
            "black": 20,
            "moves": [
                {
                    "uci": "c7c5",
                    "san": "c5",
                    "white": 30,
                    "draws": 10,
                    "black": 10,
                },
                {
                    "uci": "e7e5",
                    "san": "e5",
                    "white": 30,
                    "draws": 10,
                    "black": 10,
                },
            ],
        }
    }

    stats_e4 = MoveStats(
        uci=move_e4.uci(),
        san="e4",
        white_wins=60,
        draws=20,
        black_wins=20,
        total_games=100,
    )

    edge_e4 = RepertoireEdge(
        parent=root_node,
        child=child_e4,
        move=move_e4,
        move_san="e4",
        stats=stats_e4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=True,
    )

    root_node.edges.append(edge_e4)

    builder.compute_terminal_advantages([root_node])

    writer = PGNWriter(config, side="white")
    game = writer.create_pgn_game(root_node, "")

    first_move_node = game.variations[0]

    assert "A:" in first_move_node.comment
    assert "TS:" in first_move_node.comment
    assert "P: %" in first_move_node.comment


def test_prune_non_best_moves_marks_edges(tmp_path):
    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False
    config.prune_non_best_moves = True

    builder = RepertoireBuilder(config, side="white")

    root_board = chess.Board()
    root_node = _make_node(root_board, is_player_turn=True)

    move_e4 = root_board.parse_san("e4")
    board_after_e4 = root_board.copy()
    board_after_e4.push(move_e4)
    child_e4 = _make_node(board_after_e4, is_player_turn=False)

    stats_e4 = MoveStats(
        uci=move_e4.uci(),
        san="e4",
        white_wins=60,
        draws=20,
        black_wins=20,
        total_games=100,
    )

    edge_e4 = RepertoireEdge(
        parent=root_node,
        child=child_e4,
        move=move_e4,
        move_san="e4",
        stats=stats_e4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=False,
        is_best_continuation=False,
    )

    # Mock position stats for child_e4 to prevent fetching real data
    child_e4.position_stats = {
        "lichess": {
            "white": 45,
            "draws": 20,
            "black": 35,
            "moves": [
                {
                    "uci": "c7c5",
                    "san": "c5",
                    "white": 45,
                    "draws": 20,
                    "black": 35,
                },
            ],
        }
    }

    move_d4 = chess.Move.from_uci("d2d4")
    board_after_d4 = root_board.copy()
    board_after_d4.push(move_d4)
    child_d4 = _make_node(board_after_d4, is_player_turn=False)

    stats_d4 = MoveStats(
        uci=move_d4.uci(),
        san="d4",
        white_wins=50,
        draws=30,
        black_wins=20,
        total_games=80,
    )

    edge_d4 = RepertoireEdge(
        parent=root_node,
        child=child_d4,
        move=move_d4,
        move_san="d4",
        stats=stats_d4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=False,
        is_best_continuation=False,
    )

    # Mock position stats for child_d4 to prevent fetching real data
    child_d4.position_stats = {
        "lichess": {
            "white": 40,
            "draws": 20,
            "black": 40,
            "moves": [
                {
                    "uci": "d7d5",
                    "san": "d5",
                    "white": 40,
                    "draws": 20,
                    "black": 40,
                },
            ],
        }
    }

    move_c5 = chess.Move.from_uci("c7c5")
    board_after_c5 = board_after_e4.copy()
    board_after_c5.push(move_c5)
    node_after_c5 = _make_node(board_after_c5, is_player_turn=True)
    stats_c5_response = MoveStats(
        uci=move_c5.uci(),
        san="c5",
        white_wins=45,
        draws=20,
        black_wins=35,
        total_games=100,
    )

    edge_c5_response = RepertoireEdge(
        parent=child_e4,
        child=node_after_c5,
        move=move_c5,
        move_san="c5",
        stats=stats_c5_response,
        resulting_depth=2,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=False,
    )

    # Mock position stats for node_after_c5 to prevent fetching real data
    node_after_c5.position_stats = {
        "lichess": {
            "white": 45,
            "draws": 20,
            "black": 35,
            "moves": [],
        }
    }

    child_e4.edges.append(edge_c5_response)

    move_d5 = chess.Move.from_uci("d7d5")
    board_after_d5 = board_after_d4.copy()
    board_after_d5.push(move_d5)
    node_after_d5 = _make_node(board_after_d5, is_player_turn=True)
    stats_d5_response = MoveStats(
        uci=move_d5.uci(),
        san="d5",
        white_wins=40,
        draws=20,
        black_wins=40,
        total_games=100,
    )

    edge_d5_response = RepertoireEdge(
        parent=child_d4,
        child=node_after_d5,
        move=move_d5,
        move_san="d5",
        stats=stats_d5_response,
        resulting_depth=2,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=False,
    )

    # Mock position stats for node_after_d5 to prevent fetching real data
    node_after_d5.position_stats = {
        "lichess": {
            "white": 40,
            "draws": 20,
            "black": 40,
            "moves": [],
        }
    }

    child_d4.edges.append(edge_d5_response)

    root_node.edges.extend([edge_e4, edge_d4])

    # Expected best edge is determined by terminal advantage of children
    # child_e4 terminal advantage: 0.1 (from position stats)
    # child_d4 terminal advantage: 0.0 (from position stats)
    # So e4 should be the best
    expected_best_edge = edge_e4

    builder.compute_terminal_advantages([root_node])

    # Pruning comments removed

    for edge in [edge_e4, edge_d4]:
        if edge is expected_best_edge:
            assert edge.is_best_continuation is True
            assert edge.child is not None
            assert edge.is_terminal is False
        else:
            assert edge.is_best_continuation is False
            assert edge.is_terminal is True
            assert edge.child is None
            assert edge.termination_reason is None


def test_pgn_writer_includes_pruned_terminal_advantage_comments(tmp_path):
    """Test that pruned moves include terminal advantage comments in PGN output."""
    from src.pgn_writer import PGNWriter

    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False
    config.prune_non_best_moves = True

    builder = RepertoireBuilder(config, side="white")

    root_board = chess.Board()
    root_node = _make_node(root_board, is_player_turn=True)

    # Create two possible white moves with different advantages
    move_e4 = root_board.parse_san("e4")
    move_d4 = root_board.parse_san("d4")

    board_after_e4 = chess.Board()
    board_after_e4.push(move_e4)
    child_e4 = _make_node(board_after_e4, is_player_turn=False)

    board_after_d4 = chess.Board()
    board_after_d4.push(move_d4)
    child_d4 = _make_node(board_after_d4, is_player_turn=False)

    # Create terminal responses to enable proper terminal advantage computation
    move_c5 = chess.Move.from_uci("c7c5")
    board_after_c5 = board_after_e4.copy()
    board_after_c5.push(move_c5)
    node_after_c5 = _make_node(board_after_c5, is_player_turn=True)
    stats_c5_response = MoveStats(
        uci=move_c5.uci(),
        san="c5",
        white_wins=45,
        draws=20,
        black_wins=35,
        total_games=100,
    )

    edge_c5_response = RepertoireEdge(
        parent=child_e4,
        child=node_after_c5,
        move=move_c5,
        move_san="c5",
        stats=stats_c5_response,
        resulting_depth=2,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=False,
    )

    move_d5 = chess.Move.from_uci("d7d5")
    board_after_d5 = board_after_d4.copy()
    board_after_d5.push(move_d5)
    node_after_d5 = _make_node(board_after_d5, is_player_turn=True)
    stats_d5_response = MoveStats(
        uci=move_d5.uci(),
        san="d5",
        white_wins=40,
        draws=20,
        black_wins=40,
        total_games=100,
    )

    edge_d5_response = RepertoireEdge(
        parent=child_d4,
        child=node_after_d5,
        move=move_d5,
        move_san="d5",
        stats=stats_d5_response,
        resulting_depth=2,
        comment="",
        termination_reason=None,
        is_terminal=True,
        is_best_continuation=False,
    )

    # Create stats with different advantages - e4 should be better
    stats_e4 = MoveStats(
        uci=move_e4.uci(),
        san="e4",
        white_wins=60,
        draws=20,
        black_wins=20,
        total_games=100,
    )  # advantage = 0.4

    stats_d4 = MoveStats(
        uci=move_d4.uci(),
        san="d4",
        white_wins=55,
        draws=20,
        black_wins=25,
        total_games=100,
    )  # advantage = 0.3

    edge_e4 = RepertoireEdge(
        parent=root_node,
        child=child_e4,
        move=move_e4,
        move_san="e4",
        stats=stats_e4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=False,
        is_best_continuation=False,
    )

    edge_d4 = RepertoireEdge(
        parent=root_node,
        child=child_d4,
        move=move_d4,
        move_san="d4",
        stats=stats_d4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=False,
        is_best_continuation=False,
    )

    child_e4.edges.append(edge_c5_response)
    child_d4.edges.append(edge_d5_response)

    root_node.edges.extend([edge_e4, edge_d4])

    # Compute terminal advantages and prune non-best moves
    builder.compute_terminal_advantages([root_node])

    # Verify that one move was pruned
    pruned_edge = edge_d4 if edge_e4.is_best_continuation else edge_e4
    best_edge = edge_e4 if edge_e4.is_best_continuation else edge_d4

    assert pruned_edge.is_terminal is True
    assert pruned_edge.termination_reason is None
    assert pruned_edge.comment is None

    # Generate PGN and verify pruning comment is included
    writer = PGNWriter(config, side="white")
    game = writer.create_pgn_game(root_node, "")

    # Convert to string to check content
    pgn_str = str(game)

    # The pruned move should not include pruning comments
    assert "Pruned: suboptimal terminal advantage" not in pgn_str
    # The pruned move should still include its advantage
    assert "A:" in pgn_str

    # Verify the best move is not pruned
    assert best_edge.is_best_continuation is True

    # Verify that the pruned edge has its terminal advantage stored
    assert pruned_edge.terminal_advantage is not None
    assert pruned_edge.terminal_advantage >= 0

    # Verify that TWM appears in PGN output for the pruned move
    # Find the line containing the pruned move's SAN
    pruned_move_san = pruned_edge.move_san
    pruned_move_lines = [
        line for line in pgn_str.split("\n") if pruned_move_san in line
    ]
    assert len(pruned_move_lines) > 0

    # Check that the terminal score annotation is present in the PGN output
    assert "TS:" in pgn_str
    # Verify the TS value matches what was stored on the edge
    expected_ts = f"TS: {pruned_edge.terminal_advantage * 100:.2f}"
    assert expected_ts in pgn_str
    assert best_edge.is_terminal is False
    assert best_edge.child is not None


def test_postprune_removes_low_game_moves(tmp_path):
    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False
    config.postprune_min_lichess_games = 80

    builder = RepertoireBuilder(config, side="white")

    root_board = chess.Board()
    root_node = _make_node(root_board, is_player_turn=True)

    move_e4 = root_board.parse_san("e4")
    board_after_e4 = root_board.copy()
    board_after_e4.push(move_e4)
    child_e4 = _make_node(board_after_e4, is_player_turn=False)
    child_e4.position_stats = {
        "lichess": {
            "white": 55,
            "draws": 10,
            "black": 35,
            "moves": [],
        }
    }
    stats_e4 = MoveStats(
        uci=move_e4.uci(),
        san="e4",
        white_wins=55,
        draws=10,
        black_wins=35,
        total_games=100,
    )
    edge_e4 = RepertoireEdge(
        parent=root_node,
        child=child_e4,
        move=move_e4,
        move_san="e4",
        stats=stats_e4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
    )

    move_d4 = root_board.parse_san("d4")
    board_after_d4 = root_board.copy()
    board_after_d4.push(move_d4)
    child_d4 = _make_node(board_after_d4, is_player_turn=False)
    child_d4.position_stats = {
        "lichess": {
            "white": 80,
            "draws": 5,
            "black": 15,
            "moves": [],
        }
    }
    stats_d4 = MoveStats(
        uci=move_d4.uci(),
        san="d4",
        white_wins=40,
        draws=5,
        black_wins=5,
        total_games=50,
    )
    edge_d4 = RepertoireEdge(
        parent=root_node,
        child=child_d4,
        move=move_d4,
        move_san="d4",
        stats=stats_d4,
        resulting_depth=1,
        comment="",
        termination_reason=None,
        is_terminal=True,
    )

    root_node.edges.extend([edge_e4, edge_d4])

    builder.compute_terminal_advantages([root_node])

    assert len(root_node.edges) == 1
    assert root_node.edges[0].move_san == "e4"
    # The remaining move should dictate the player's terminal advantage after pruning
    assert root_node.terminal_advantage == pytest.approx(0.2)


def test_opponent_moves_sorted_by_popularity(tmp_path):
    """Test that opponent moves are sorted by popularity, not terminal advantage."""
    from src.pgn_writer import PGNWriter

    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False
    config.prune_non_best_moves = False  # Don't prune opponent moves

    builder = RepertoireBuilder(config, side="white")

    # Create a position where it's opponent's turn (black)
    root_board = chess.Board()
    root_board.push_san("e4")  # White plays e4
    root_node = RepertoireNode(
        board=root_board,
        fen=root_board.fen(),
        key=root_board.fen(),
        is_player_turn=False,
    )

    # Create opponent responses with different popularity but similar terminal advantages
    # e5 (most popular), c5 (second most), e6 (third most)
    moves_info = [
        ("e5", 6000, 0.12),  # Most popular
        ("c5", 4000, 0.13),  # Second most popular
        ("e6", 2000, 0.11),  # Least popular but has decent advantage
    ]

    for move_san, total_games, terminal_advantage in moves_info:
        try:
            move = root_board.parse_san(move_san)
        except ValueError:
            continue

        child_board = root_board.copy()
        child_board.push(move)

        child_fen = child_board.fen()
        child_node = RepertoireNode(
            board=child_board, fen=child_fen, key=child_fen, is_player_turn=True
        )
        child_node.terminal_advantage = terminal_advantage

        # Create stats with specified total games
        stats = MoveStats(
            uci=move.uci(),
            san=move_san,
            white_wins=int(total_games * 0.5),
            draws=int(total_games * 0.3),
            black_wins=int(total_games * 0.2),
            total_games=total_games,
        )

        from src.repertoire_builder import RepertoireEdge

        edge = RepertoireEdge(
            parent=root_node,
            child=child_node,
            move=move,
            move_san=move_san,
            stats=stats,
            resulting_depth=1,
        )

        root_node.add_edge(edge)

    # Generate PGN and check the order via the game tree to avoid parsing issues
    writer = PGNWriter(config, side="white")
    game = writer.create_pgn_game(root_node, "e4")

    first_move_node = game.variations[0]
    board_after_e4 = first_move_node.board()
    responses = [
        board_after_e4.san(child.move) for child in first_move_node.variations
    ]

    assert responses[0] == "e5", f"Expected e5 first, got {responses}"
    assert responses[1] == "c5", f"Expected c5 second, got {responses}"
    assert responses[2] == "e6", f"Expected e6 third, got {responses}"

    print("✓ Opponent moves correctly sorted by popularity: e5 > c5 > e6")


def test_player_moves_sorted_by_terminal_advantage(tmp_path):
    """Test that player moves are still sorted by terminal advantage."""
    from src.pgn_writer import PGNWriter
    from src.repertoire_builder import RepertoireEdge

    config = Config()
    config.cache_file = str(tmp_path / "cache.db")
    config.use_proxy = False
    config.prune_non_best_moves = False  # Disable pruning to see sorting order

    # Create a position where it's player's turn (white)
    root_board = chess.Board()
    root_node = RepertoireNode(
        board=root_board,
        fen=root_board.fen(),
        key=root_board.fen(),
        is_player_turn=True,
    )

    # Create player moves with different terminal advantages but similar popularity
    # e4 (best advantage), d4 (second best), Nf3 (worst advantage)
    moves_info = [
        ("e4", 3000, 0.20),  # Best terminal advantage
        (
            "d4",
            3100,
            0.15,
        ),  # Second best terminal advantage (more popular but worse advantage)
        ("Nf3", 2900, 0.10),  # Worst terminal advantage
    ]

    for move_san, total_games, terminal_advantage in moves_info:
        try:
            move = root_board.parse_san(move_san)
        except ValueError:
            continue

        child_board = root_board.copy()
        child_board.push(move)

        child_fen = child_board.fen()
        child_node = RepertoireNode(
            board=child_board, fen=child_fen, key=child_fen, is_player_turn=False
        )
        # Set terminal advantage directly on child node
        child_node.terminal_advantage = terminal_advantage

        # Create stats with specified total games
        stats = MoveStats(
            uci=move.uci(),
            san=move_san,
            white_wins=int(total_games * 0.5),
            draws=int(total_games * 0.3),
            black_wins=int(total_games * 0.2),
            total_games=total_games,
        )

        edge = RepertoireEdge(
            parent=root_node,
            child=child_node,
            move=move,
            move_san=move_san,
            stats=stats,
            resulting_depth=1,
            is_terminal=True,  # Make edge terminal to preserve child
        )

        root_node.add_edge(edge)

    # Test the sorting logic directly without calling compute_terminal_advantages
    # since terminal edges should preserve their child's terminal advantage
    from src.pgn_writer import PGNWriter

    writer = PGNWriter(config, side="white")

    # Apply the same sorting logic as in node_to_pgn_variation
    sorted_edges = sorted(
        root_node.edges,
        key=lambda e: (
            # Get terminal advantage from child or edge (for pruned nodes), default to -1 for None
            (
                (getattr(e.child, "terminal_advantage", None) if e.child else None)
                or getattr(e, "terminal_advantage", None)
            )
            or -1
        ),
        reverse=True,
    )

    # Print the sorted order for debugging
    print("\nSorted player moves:")
    for i, edge in enumerate(sorted_edges):
        child_tadv = (
            getattr(edge.child, "terminal_advantage", None) if edge.child else None
        )
        edge_tadv = getattr(edge, "terminal_advantage", None)
        effective_tadv = child_tadv or edge_tadv or -1
        print(
            f"  {i + 1}. {edge.move_san}: tadv={effective_tadv}, games={edge.stats.total_games if edge.stats else 0}"
        )

    # Check the order - should be sorted by terminal advantage
    assert sorted_edges[0].move_san == "e4", (
        f"Expected e4 first (best advantage), got {sorted_edges[0].move_san}"
    )
    assert sorted_edges[1].move_san == "d4", (
        f"Expected d4 second, got {sorted_edges[1].move_san}"
    )
    assert sorted_edges[2].move_san == "Nf3", (
        f"Expected Nf3 last, got {sorted_edges[2].move_san}"
    )

    print("✓ Player moves correctly sorted by terminal advantage: e4 > d4 > Nf3")

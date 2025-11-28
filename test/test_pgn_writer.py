from pathlib import Path

import chess

from src.config import Config
from src.models.graph import RepertoireEdge, RepertoireNode
from src.models.stats import MoveStats
from src.services.pgn_writer import PGNWriter, extract_and_format_stats_comment


def make_root_after_moves(moves: str) -> RepertoireNode:
    board = chess.Board()
    for token in moves.split():
        board.push(board.parse_san(token))

    return RepertoireNode(
        board=board.copy(),
        fen=board.fen(),
        key=f"root-{moves}",
        is_player_turn=board.turn == chess.WHITE,
        terminal_advantage=0.2,
    )


def test_write_repertoire_creates_one_file_per_initial_moves(tmp_path):
    writer = PGNWriter(Config(), side="white")
    initial_sequences = ["e4", "d4"]
    roots = [make_root_after_moves(seq) for seq in initial_sequences]

    base_output = tmp_path / "repertoire_white.pgn"
    paths = writer.write_repertoire(roots, str(base_output), initial_sequences)

    assert len(paths) == 2
    names = {Path(p).name for p in paths}
    assert names == {"repertoire_white-e4.pgn", "repertoire_white-d4.pgn"}

    for path, initial in zip(paths, initial_sequences):
        data = Path(path).read_text()
        assert f'InitialMoves "{initial}"' in data

    assert not base_output.exists()


def test_comment_formatting():
    # Setup parent node with stats for popularity calculation
    parent = RepertoireNode(
        board=chess.Board(),
        fen=chess.STARTING_FEN,
        key="start",
        is_player_turn=True,
        position_stats={
            "lichess": {"white": 40, "draws": 20, "black": 40}
        },  # Total 100
    )

    # Setup child node
    child = RepertoireNode(
        board=chess.Board(),
        fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        key="e4",
        is_player_turn=False,
        terminal_advantage=0.5,
    )

    # Setup edge with stats
    # White wins 30, Black wins 10, Draws 10. Total 50.
    # White win rate: 0.6. Black win rate: 0.2.
    # Advantage (White): 0.6 - 0.2 = 0.4.
    stats = MoveStats(
        uci="e2e4",
        san="e4",
        white_wins=30,
        draws=10,
        black_wins=10,
        total_games=50,  # 50/100 = 50% popularity
    )

    edge = RepertoireEdge(
        parent=parent,
        child=child,
        move=chess.Move.from_uci("e2e4"),
        move_san="e4",
        stats=stats,
        resulting_depth=1,
        is_terminal=False,
    )

    # Test formatting for White side
    comment = extract_and_format_stats_comment(edge, is_white=True)

    # Expected: A: 40.00, T: 50.00, P: 50.00%
    assert "A: 40.00" in comment
    assert "T: 50.00" in comment
    assert "P: 50.00%" in comment

    # Test formatting for Black side
    # Advantage for black: 0.2 - 0.6 = -0.4
    comment_black = extract_and_format_stats_comment(edge, is_white=False)
    assert "A: -40.00" in comment_black

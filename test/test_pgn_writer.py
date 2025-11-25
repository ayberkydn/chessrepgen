from pathlib import Path

import chess

from src.config import Config
from src.pgn_writer import PGNWriter
from src.repertoire_builder import RepertoireNode


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

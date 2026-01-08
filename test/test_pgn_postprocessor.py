"""Tests for PGN postprocessor."""

import textwrap
from pathlib import Path

import chess.pgn
import pytest

from src.services.pgn_postprocessor import PGNPostprocessor


def test_filter_comment_fields():
    """Test granular comment field removal with new minified format."""
    processor = PGNPostprocessor()

    # Test removing advantage (new format)
    processor.remove_advantage = True
    comment = "A:5.0,T:10.0,P:25.0%,G:1500"
    result = processor._filter_comment_fields(comment)
    assert result == "T:10.0,P:25.0%,G:1500"
    assert "A:" not in result

    # Test removing terminal advantage
    processor = PGNPostprocessor()
    processor.remove_terminal_advantage = True
    result = processor._filter_comment_fields(comment)
    assert result == "A:5.0,P:25.0%,G:1500"
    assert "T:" not in result

    # Test removing popularity
    processor = PGNPostprocessor()
    processor.remove_popularity = True
    result = processor._filter_comment_fields(comment)
    assert result == "A:5.0,T:10.0,G:1500"
    assert "P:" not in result

    # Test removing game count
    processor = PGNPostprocessor()
    processor.remove_game_count = True
    result = processor._filter_comment_fields(comment)
    assert result == "A:5.0,T:10.0,P:25.0%"
    assert "G:" not in result

    # Test removing alternatives
    processor = PGNPostprocessor()
    processor.remove_alternatives = True
    comment_with_alts = "A:5.0,T:10.0,P:25.0%,G:1500,Alts:Nf3 4.5,d4 3.2"
    result = processor._filter_comment_fields(comment_with_alts)
    assert result == "A:5.0,T:10.0,P:25.0%,G:1500"
    assert "Alts:" not in result

    # Test removing multiple fields
    processor = PGNPostprocessor()
    processor.remove_advantage = True
    processor.remove_game_count = True
    processor.remove_alternatives = True
    result = processor._filter_comment_fields(comment_with_alts)
    assert result == "T:10.0,P:25.0%"
    assert "A:" not in result
    assert "G:" not in result
    assert "Alts:" not in result

    # Test removing all fields leaves empty string
    processor = PGNPostprocessor(
        remove_advantage=True,
        remove_terminal_advantage=True,
        remove_popularity=True,
        remove_game_count=True,
        remove_alternatives=True,
    )
    result = processor._filter_comment_fields(comment_with_alts)
    assert result == ""


def test_filter_comment_fields_old_format():
    """Test granular comment field removal with old spaced format."""
    # Old format: "A: 5.00, T: 10.00, P: 25.00%, G: 1500"
    processor = PGNPostprocessor()

    # Test removing game count and popularity (old format)
    processor.remove_game_count = True
    processor.remove_popularity = True
    comment = "A: 1.75, T: 32.07, P: 31.49%, G: 99902423"
    result = processor._filter_comment_fields(comment)
    assert result == "A:1.75,T:32.07"
    assert "G:" not in result
    assert "P:" not in result

    # Test removing alternatives (old format)
    processor = PGNPostprocessor(remove_alternatives=True)
    comment_with_alts = "A: 5.00, T: 10.00, Alts: Nf3 4.50, d4 3.20"
    result = processor._filter_comment_fields(comment_with_alts)
    assert result == "A:5.00,T:10.00"
    assert "Alts:" not in result

    # Test removing all fields (old format)
    processor = PGNPostprocessor(
        remove_advantage=True,
        remove_terminal_advantage=True,
        remove_popularity=True,
        remove_game_count=True,
        remove_alternatives=True,
    )
    result = processor._filter_comment_fields(
        "A: 1.75, T: 32.07, P: 31.49%, G: 99902423"
    )
    assert result == ""


def test_process_filters_by_initial_moves_and_splits_outputs(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "?"]
            [Black "?"]
            [Result "*"]
            [InitialMoves "e4"]

            1. e4 e5 2. Nf3 Nc6 *

            [Event "Test"]
            [White "?"]
            [Black "?"]
            [Result "*"]
            [InitialMoves "d4 c6"]

            1. d4 c6 2. c4 d5 *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(initial_lines=["e4", "d4 c6"])
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 2
    names = {Path(path).name for path in outputs}
    assert names == {"processed-e4.pgn", "processed-d4-c6.pgn"}
    assert not (tmp_path / "processed.pgn").exists()

    data_first = Path(outputs[0]).read_text()
    assert 'InitialMoves "e4"' in data_first
    assert 'InitialMoves "d4 c6"' not in data_first
    assert data_first.count("InitialMoves") == 1

    data_second = Path(outputs[1]).read_text()
    assert 'InitialMoves "d4 c6"' in data_second
    assert 'InitialMoves "e4"' not in data_second
    assert data_second.count("InitialMoves") == 1


def test_process_raises_when_initial_moves_not_found(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "?"]
            [Black "?"]
            [Result "*"]
            [InitialMoves "e4"]

            1. e4 e5 2. Nf3 Nc6 *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(initial_lines=["c4"])
    with pytest.raises(ValueError, match="Initial moves not found"):
        processor.process(str(input_file), str(tmp_path / "processed.pgn"))


def test_prune_non_best_moves_keeps_best_player_line(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "Repertoire"]
            [Black "Opponent"]
            [Result "*"]
            [RepertoireSide "white"]

            1. e4 {T:20.0} ( 1. Nf3 {T:15.0} ) ( 1. d4 {T:5.0} ) 1... c5 *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(prune_non_best_moves=True)
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    with Path(outputs[0]).open() as f:
        game = chess.pgn.read_game(f)

    assert len(game.variations) == 1
    first_move = game.variations[0]
    assert "Alts:Nf3 15.0,d4 5.0" in first_move.comment
    data = Path(outputs[0]).read_text()
    assert "( 1. Nf3" not in data
    assert "( 1. d4" not in data


def test_prune_non_best_moves_skips_opponent_responses(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "Repertoire"]
            [Black "Opponent"]
            [Result "*"]
            [RepertoireSide "white"]

            1. e4 {T:20.0} 1... c5 {T:5.0} ( 1... e5 {T:15.0} 2. Nc3 {T:18.0} ) 2. Nf3 {T:22.0} *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(prune_non_best_moves=True)
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    with Path(outputs[0]).open() as f:
        game = chess.pgn.read_game(f)

    first_move = game.variations[0]
    assert len(first_move.variations) == 2


def test_prune_non_best_moves_handles_black_repertoire(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "Opponent"]
            [Black "Repertoire"]
            [Result "*"]
            [RepertoireSide "black"]

            1. e4 e5 {T:10.0} ( 1... c5 {T:5.0} ) *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(prune_non_best_moves=True)
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    with Path(outputs[0]).open() as f:
        game = chess.pgn.read_game(f)

    opponent_move = game.variations[0]
    assert len(opponent_move.variations) == 1
    best_reply = opponent_move.variations[0]
    assert "Alts:c5 5.0" in best_reply.comment
def test_postprocess_lines_end_with_player_move_white(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "Repertoire"]
            [Black "Opponent"]
            [Result "*"]
            [RepertoireSide "white"]
            [InitialMoves "e4"]

            1. e4 c5 2. Nf3 d6 *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor()
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    with Path(outputs[0]).open() as f:
        game = chess.pgn.read_game(f)
    end_node = game.end()
    board = end_node.board()
    assert board.turn is False  # black to move, last move by white repertoire


def test_postprocess_lines_end_with_player_move_black(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "Opponent"]
            [Black "Repertoire"]
            [Result "*"]
            [RepertoireSide "black"]
            [InitialMoves "d4 d5"]

            1. d4 d5 2. c4 e6 3. Nc3 *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor()
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    with Path(outputs[0]).open() as f:
        game = chess.pgn.read_game(f)
    end_node = game.end()
    board = end_node.board()
    assert board.turn is True  # white to move, last move by black repertoire


def test_numbered_initial_moves_are_normalized(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "Repertoire"]
            [Black "Opponent"]
            [Result "*"]
            [RepertoireSide "white"]
            [InitialMoves "1. e4 e6 2. d4 d5"]

            1. e4 e6 2. d4 d5 3. Nc3 Nf6 *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(initial_lines=["e4 e6 d4 d5"])
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    assert Path(outputs[0]).read_text().count("InitialMoves") == 1


def test_initial_moves_match_mainline_prefix_when_header_shorter(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    # Header only includes the first two plies, but the mainline contains the full sequence.
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "Repertoire"]
            [Black "Opponent"]
            [Result "*"]
            [RepertoireSide "white"]
            [InitialMoves "e4 e6"]

            1. e4 e6 2. d4 d5 3. Nc3 Nf6 *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(initial_lines=["e4 e6 d4 d5"])
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    assert Path(outputs[0]).read_text().count("InitialMoves") == 1


def test_initial_moves_match_variation_branch(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "Repertoire"]
            [Black "Opponent"]
            [Result "*"]
            [RepertoireSide "white"]
            [InitialMoves "e4"]

            1. e4 c5 ( 1... e6 2. d4 d5 3. Nc3 Nf6 ) *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(initial_lines=["e4 e6 d4 d5"])
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    assert Path(outputs[0]).read_text().count("InitialMoves") == 1


def test_filter_excludes_other_games_when_initial_lines_provided(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "?"]
            [Black "?"]
            [Result "*"]
            [InitialMoves "e4 e6"]

            1. e4 e6 2. d4 d5 *

            [Event "Test"]
            [White "?"]
            [Black "?"]
            [Result "*"]
            [InitialMoves "e4 e5"]

            1. e4 e5 2. Nf3 Nc6 *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(initial_lines=["e4 e6"])
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    data = Path(outputs[0]).read_text()
    assert data.count('InitialMoves "e4 e6"') == 1
    assert 'InitialMoves "e4 e5"' not in data


def test_add_move_indicators_symbols(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "?"]
            [Black "?"]
            [Result "*"]
            [RepertoireSide "white"]

            1. e4 {T:10.0} e5 {T:0.0} 2. Nf3 {T:0.0} 2... Nc6 {T:7.0} 3. Bb5 {T:7.0} *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(add_move_indicators=True, use_nag_codes=False)
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    data = Path(outputs[0]).read_text()
    assert "e5!" in data
    assert "Nc6?!" in data
    assert "e4!" not in data
    assert "Nf3!" not in data
    assert "Nf3?" not in data
    assert "$1" not in data


def test_add_move_indicators_codes(tmp_path):
    input_file = tmp_path / "repertoire.pgn"
    input_file.write_text(
        textwrap.dedent(
            """
            [Event "Test"]
            [White "?"]
            [Black "?"]
            [Result "*"]
            [RepertoireSide "white"]

            1. e4 {T:10.0} e5 {T:0.0} 2. Nf3 {T:0.0} 2... Nc6 {T:7.0} 3. Bb5 {T:7.0} *
            """
        ).strip()
        + "\n"
    )

    processor = PGNPostprocessor(add_move_indicators=True, use_nag_codes=True)
    outputs = processor.process(str(input_file), str(tmp_path / "processed.pgn"))

    assert len(outputs) == 1
    data = Path(outputs[0]).read_text()
    assert "e5 $1" in data
    assert "Nc6 $6" in data
    assert "e4 $1" not in data
    assert "Nf3 $5" not in data

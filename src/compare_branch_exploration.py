#!/usr/bin/env python3
"""Compare two repertoire PGNs and highlight differences in best player moves."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import chess
import chess.pgn


@dataclass
class BestMoveRecord:
    line: list[str]
    move: str | None


@dataclass
class BestMoveDifference:
    fen: str
    line: list[str]
    first_move: str | None
    second_move: str | None


def determine_player_color(game: chess.pgn.Game, preference: str) -> chess.Color:
    """Return the color considered to be the repertoire player."""

    if preference == "auto":
        header_value = (game.headers.get("RepertoireSide") or "").strip().lower()
        preference = header_value if header_value in {"white", "black"} else "white"

    return chess.WHITE if preference == "white" else chess.BLACK


def _collect_best_moves(
    node: chess.pgn.GameNode,
    board: chess.Board,
    player_color: chess.Color,
    current_line: list[str],
    results: dict[str, BestMoveRecord],
) -> None:
    """Traverse PGN tree, recording only the main player move at each decision."""

    if board.turn == player_color:
        fen = board.fen()
        best_move = None
        children: list[chess.pgn.GameNode] = []

        if node.variations:
            best_child = node.variations[0]
            best_move = board.san(best_child.move)
            children = [best_child]
        else:
            children = []

        record = results.get(fen)
        if not record:
            results[fen] = BestMoveRecord(line=list(current_line), move=best_move)
        elif record.move is None and best_move is not None:
            record.move = best_move

    else:
        children = list(node.variations)

    for child in children:
        san = board.san(child.move)
        board.push(child.move)
        current_line.append(san)
        _collect_best_moves(child, board, player_color, current_line, results)
        current_line.pop()
        board.pop()


def parse_best_moves(path: Path, player_side: str) -> dict[str, BestMoveRecord]:
    """Map each player decision to its best (main-line) move."""

    results: dict[str, BestMoveRecord] = {}
    with path.open() as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            color = determine_player_color(game, player_side)
            board = game.board()
            _collect_best_moves(game, board, color, [], results)
    return results


def summarize_positions(records: dict[str, BestMoveRecord]) -> tuple[int, int]:
    """Return counts of player nodes and those with an explored best move."""

    total_nodes = len(records)
    explored = sum(1 for record in records.values() if record.move is not None)
    return total_nodes, explored


def collect_differences(
    first: dict[str, BestMoveRecord],
    second: dict[str, BestMoveRecord],
) -> list[BestMoveDifference]:
    diffs: list[BestMoveDifference] = []
    all_keys = set(first) | set(second)
    for fen in all_keys:
        record_a = first.get(fen)
        record_b = second.get(fen)
        move_a = record_a.move if record_a else None
        move_b = record_b.move if record_b else None
        if move_a == move_b:
            continue

        line = (
            list(record_a.line)
            if record_a and record_a.line
            else (list(record_b.line) if record_b else [])
        )
        diffs.append(
            BestMoveDifference(
                fen=fen,
                line=line,
                first_move=move_a,
                second_move=move_b,
            )
        )
    return diffs


def format_line(line: Iterable[str]) -> str:
    return " ".join(line) if line else "(start)"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two PGNs and report differences in best player moves"
    )
    parser.add_argument("first", help="Baseline PGN path")
    parser.add_argument("second", help="Comparison PGN path")
    parser.add_argument(
        "--player-side",
        choices=["auto", "white", "black"],
        default="auto",
        help="Which color represents the repertoire player (default: auto)",
    )
    parser.add_argument(
        "--label-first", default="first", help="Label used for the baseline PGN"
    )
    parser.add_argument(
        "--label-second", default="second", help="Label used for the comparison PGN"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="How many detailed differences to print (default: 25)",
    )

    args = parser.parse_args()

    first_path = Path(args.first)
    second_path = Path(args.second)
    if not first_path.exists() or not second_path.exists():
        parser.error("Both PGN paths must exist")

    print(f"Loading {args.label_first}: {first_path}")
    first_best = parse_best_moves(first_path, args.player_side)
    print(f"Loading {args.label_second}: {second_path}")
    second_best = parse_best_moves(second_path, args.player_side)

    first_nodes, first_explored = summarize_positions(first_best)
    second_nodes, second_explored = summarize_positions(second_best)
    print()
    print(
        f"{args.label_first}: {first_nodes} player nodes, {first_explored} best moves"
    )
    print(
        f"{args.label_second}: {second_nodes} player nodes, {second_explored} best moves"
    )

    differences = collect_differences(first_best, second_best)
    differences = [
        diff
        for diff in differences
        if diff.first_move is not None and diff.second_move is not None
    ]
    differences.sort(key=lambda diff: len(diff.line))

    print()
    print(f"Positions with differing best moves: {len(differences)}")

    if args.limit <= 0 or not differences:
        return 0

    print()
    print("Detailed best-move differences:")
    for diff in differences[: args.limit]:
        print(f"Line: {format_line(diff.line)}")
        print(f"FEN: {diff.fen}")
        move_first = diff.first_move or "(stops here)"
        move_second = diff.second_move or "(stops here)"
        print(f"  {args.label_first}: {move_first}")
        print(f"  {args.label_second}: {move_second}")
        print("---")

    remaining = len(differences) - args.limit
    if remaining > 0:
        print(f"({remaining} additional positions with differences not shown)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

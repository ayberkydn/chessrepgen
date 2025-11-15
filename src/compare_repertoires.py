#!/usr/bin/env python3
"""Compare two repertoire PGNs and report player-move differences."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import chess
import chess.pgn


@dataclass
class PositionRecord:
    moves: set[str]
    line: list[str]


@dataclass
class Difference:
    fen: str
    line: list[str]
    moves_a: set[str]
    moves_b: set[str]


def determine_player_color(game: chess.pgn.Game, preference: str) -> chess.Color:
    """Pick which side represents the repertoire player for a game."""

    if preference == "auto":
        header = (game.headers.get("RepertoireSide") or "").strip().lower()
        preference = header if header in {"white", "black"} else "white"

    return chess.WHITE if preference == "white" else chess.BLACK


def _collect_positions(
    node: chess.pgn.GameNode,
    board: chess.Board,
    player_color: chess.Color,
    current_line: list[str],
    results: dict[str, PositionRecord],
) -> None:
    if board.turn == player_color and node.variations:
        fen = board.fen()
        record = results.get(fen)
        if not record:
            record = PositionRecord(moves=set(), line=list(current_line))
            results[fen] = record
        elif not record.line:
            record.line = list(current_line)

        for child in node.variations:
            record.moves.add(board.san(child.move))

    for child in node.variations:
        san = board.san(child.move)
        board.push(child.move)
        current_line.append(san)
        _collect_positions(child, board, player_color, current_line, results)
        current_line.pop()
        board.pop()


def parse_repertoire_positions(
    path: Path, player_side: str = "auto"
) -> dict[str, PositionRecord]:
    """Map each player decision FEN to the set of SAN moves seen in the PGN."""

    results: dict[str, PositionRecord] = {}
    with path.open() as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            color = determine_player_color(game, player_side)
            board = game.board()
            _collect_positions(game, board, color, [], results)
    return results


def diff_positions(
    first: dict[str, PositionRecord],
    second: dict[str, PositionRecord],
) -> list[Difference]:
    diffs: list[Difference] = []
    all_keys = set(first) | set(second)
    for fen in all_keys:
        moves_a = first.get(fen).moves if fen in first else set()
        moves_b = second.get(fen).moves if fen in second else set()
        if moves_a == moves_b:
            continue
        baseline = first.get(fen) or second.get(fen)
        diffs.append(
            Difference(
                fen=fen,
                line=list(baseline.line if baseline else []),
                moves_a=set(moves_a),
                moves_b=set(moves_b),
            )
        )
    return diffs


def summarize_differences(diffs: Iterable[Difference]) -> tuple[int, int, int]:
    a_only = b_only = both = 0
    for diff in diffs:
        has_a = bool(diff.moves_a)
        has_b = bool(diff.moves_b)
        if has_a and not has_b:
            a_only += 1
        elif has_b and not has_a:
            b_only += 1
        else:
            both += 1
    return a_only, b_only, both


def format_line(line: Iterable[str]) -> str:
    return " ".join(line) if line else "(start)"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two repertoire PGNs and report move differences"
    )
    parser.add_argument("first", help="Path to the baseline PGN")
    parser.add_argument("second", help="Path to the comparison PGN")
    parser.add_argument(
        "--player-side",
        choices=["auto", "white", "black"],
        default="auto",
        help="Which side represents the repertoire player (default: auto)",
    )
    parser.add_argument(
        "--label-first", default="first", help="Label to use for the first PGN"
    )
    parser.add_argument(
        "--label-second", default="second", help="Label to use for the second PGN"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Limit the number of detailed differences shown (default: 20)",
    )

    args = parser.parse_args()

    first_path = Path(args.first)
    second_path = Path(args.second)
    if not first_path.exists() or not second_path.exists():
        parser.error("Both PGN paths must exist")

    print(f"Loading {args.label_first}: {first_path}")
    first_positions = parse_repertoire_positions(first_path, args.player_side)
    print(f"Loading {args.label_second}: {second_path}")
    second_positions = parse_repertoire_positions(second_path, args.player_side)

    print()
    print(f"{args.label_first}: {len(first_positions)} player nodes")
    print(f"{args.label_second}: {len(second_positions)} player nodes")

    differences = diff_positions(first_positions, second_positions)
    a_only, b_only, both = summarize_differences(differences)
    print(f"Changed player positions: {len(differences)}")
    print(f"  Only {args.label_first}: {a_only}")
    print(f"  Only {args.label_second}: {b_only}")
    print(f"  Different moves in both: {both}")

    if args.limit <= 0:
        return 0

    print()
    print("Detailed differences:")
    for diff in differences[: args.limit]:
        print(f"Line: {format_line(diff.line)}")
        print(f"FEN: {diff.fen}")
        moves_a = ", ".join(sorted(diff.moves_a)) or "(none)"
        moves_b = ", ".join(sorted(diff.moves_b)) or "(none)"
        print(f"  {args.label_first}: {moves_a}")
        print(f"  {args.label_second}: {moves_b}")
        print("---")

    remaining = len(differences) - args.limit
    if remaining > 0:
        print(f"({remaining} additional differences not shown)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

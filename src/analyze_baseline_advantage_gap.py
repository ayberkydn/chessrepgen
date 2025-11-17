#!/usr/bin/env python3
"""Compare baseline-advantage moves against terminal-best moves in a PGN."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import chess
import chess.pgn

ADV_REGEX = re.compile(r"A:\s*([+-]?\d+(?:\.\d+)?)")
TS_REGEX = re.compile(r"TS:\s*([+-]?\d+(?:\.\d+)?)")
POP_REGEX = re.compile(r"P:\s*%?\s*([+-]?\d+(?:\.\d+)?)")


@dataclass
class Candidate:
    idx: int
    san: str
    advantage: float | None
    terminal_score: float | None
    popularity: float | None
    node: chess.pgn.GameNode


@dataclass
class GapRecord:
    line: list[str]
    fen: str
    baseline: Candidate
    baseline_pop: float
    best_terminal: Candidate
    diff: float


def determine_player_color(game: chess.pgn.Game, preference: str) -> chess.Color:
    """Return the color treated as the repertoire player."""

    if preference == "auto":
        header_value = (game.headers.get("RepertoireSide") or "").strip().lower()
        preference = header_value if header_value in {"white", "black"} else "white"

    return chess.WHITE if preference == "white" else chess.BLACK


def parse_comment(comment: str | None) -> tuple[float | None, float | None, float | None]:
    """Extract advantage, terminal score, and popularity from a PGN comment."""

    if not comment:
        return None, None, None

    adv = float(match.group(1)) if (match := ADV_REGEX.search(comment)) else None
    ts = float(match.group(1)) if (match := TS_REGEX.search(comment)) else None
    pop = float(match.group(1)) if (match := POP_REGEX.search(comment)) else None
    return adv, ts, pop


def collect_candidates(node: chess.pgn.GameNode, board: chess.Board) -> list[Candidate]:
    candidates: list[Candidate] = []
    for idx, child in enumerate(node.variations):
        san = board.san(child.move)
        adv, ts, pop = parse_comment(child.comment)
        candidates.append(
            Candidate(
                idx=idx,
                san=san,
                advantage=adv,
                terminal_score=ts,
                popularity=pop,
                node=child,
            )
        )
    return candidates


def best_candidate(candidates: Iterable[Candidate], key: callable) -> Candidate | None:
    best: Candidate | None = None
    best_value = None
    for cand in candidates:
        value = key(cand)
        if best is None or value > best_value:
            best = cand
            best_value = value
    return best


def analyze_game(
    game: chess.pgn.Game,
    repertoire_color: chess.Color,
    baseline_threshold: float,
) -> list[GapRecord]:
    board = game.board()
    line: list[str] = []
    records: list[GapRecord] = []

    def walk(node: chess.pgn.GameNode) -> None:
        if board.turn == repertoire_color and node.variations:
            candidates = collect_candidates(node, board)

            baseline_candidates = [
                cand
                for cand in candidates
                if cand.popularity is not None
                and cand.popularity >= baseline_threshold
                and cand.advantage is not None
            ]

            if baseline_candidates:
                baseline = best_candidate(
                    baseline_candidates,
                    lambda c: (c.advantage if c.advantage is not None else float("-inf"), -c.idx),
                )
            else:
                baseline = None

            terminal_candidates = [c for c in candidates if c.terminal_score is not None]
            best_terminal = best_candidate(
                terminal_candidates,
                lambda c: (c.terminal_score if c.terminal_score is not None else float("-inf"), -c.idx),
            )

            if (
                baseline
                and best_terminal
                and best_terminal.advantage is not None
                and baseline.advantage is not None
            ):
                diff = baseline.advantage - best_terminal.advantage
                if diff > 0:
                    records.append(
                        GapRecord(
                            line=list(line),
                            fen=board.fen(),
                            baseline=baseline,
                            baseline_pop=baseline.popularity or 0.0,
                            best_terminal=best_terminal,
                            diff=diff,
                        )
                    )

        for child in node.variations:
            san = board.san(child.move)
            board.push(child.move)
            line.append(san)
            walk(child)
            line.pop()
            board.pop()

    walk(game)
    return records


def format_line(line: Iterable[str]) -> str:
    return " ".join(line) if line else "(start)"


def format_value(value: float | None) -> str:
    return f"{value:+.2f}" if value is not None else "N/A"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Identify positions where the baseline (>=10% popularity) advantage "
            "beats the move chosen for best terminal score."
        )
    )
    parser.add_argument("pgn", help="Repertoire PGN to analyze")
    parser.add_argument(
        "--player-side",
        choices=["auto", "white", "black"],
        default="auto",
        help="Color treated as the repertoire player (default: auto)",
    )
    parser.add_argument(
        "--baseline-pop",
        type=float,
        default=0.10,
        help="Minimum popularity (0-1) for baseline candidates (default: 0.10)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of top differences to display",
    )

    args = parser.parse_args()

    if not 0 <= args.baseline_pop <= 1:
        parser.error("--baseline-pop must be between 0 and 1")

    path = Path(args.pgn)
    if not path.exists():
        parser.error(f"PGN not found: {path}")

    all_records: list[GapRecord] = []
    with path.open() as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            player_color = determine_player_color(game, args.player_side)
            all_records.extend(analyze_game(game, player_color, args.baseline_pop))

    if not all_records:
        print("No positions where baseline advantage exceeded the terminal-best move.")
        return 0

    all_records.sort(key=lambda rec: rec.diff, reverse=True)

    print(f"Positions with baseline-vs-terminal advantage conflicts: {len(all_records)}")
    print(f"Largest advantage difference: {all_records[0].diff:.2f}")
    print()

    for record in all_records[: args.limit]:
        print(f"Line: {format_line(record.line)}")
        print(f"FEN: {record.fen}")
        base_adv = format_value(record.baseline.advantage)
        base_ts = format_value(record.baseline.terminal_score)
        base_pop = f"{record.baseline_pop * 100:.1f}%"
        print(
            f"  Baseline: {record.baseline.san} (Adv {base_adv}, TS {base_ts}, Pop {base_pop})"
        )
        best_adv = format_value(record.best_terminal.advantage)
        best_ts = format_value(record.best_terminal.terminal_score)
        print(
            f"  Terminal best: {record.best_terminal.san} (Adv {best_adv}, TS {best_ts})"
        )
        print(f"  Advantage difference: {record.diff:.2f}")
        print("---")

    remaining = len(all_records) - args.limit
    if remaining > 0:
        print(f"({remaining} additional positions not shown)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

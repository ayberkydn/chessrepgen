#!/usr/bin/env python3
"""Report positions where the terminal-best move had worse immediate advantage."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import chess
import chess.pgn

ADV_REGEX = re.compile(r"A:\s*([+-]?\d+(?:\.\d+)?)")
TADV_REGEX = re.compile(r"(?:TS|T):\s*([+-]?\d+(?:\.\d+)?)")


@dataclass
class Candidate:
    idx: int
    san: str
    adv: float | None
    tadv: float | None
    node: chess.pgn.GameNode


@dataclass
class GapRecord:
    line: list[str]
    fen: str
    terminal: Candidate
    immediate: Candidate
    gap: float


def determine_player_color(game: chess.pgn.Game, preference: str) -> chess.Color:
    """Infer the repertoire color."""

    if preference == "auto":
        header = (game.headers.get("RepertoireSide") or "").strip().lower()
        preference = header if header in {"white", "black"} else "white"

    return chess.WHITE if preference == "white" else chess.BLACK


def parse_advantages(comment: str | None) -> tuple[float | None, float | None]:
    """Extract A/TS float values from a PGN comment."""

    if not comment:
        return None, None

    adv_match = ADV_REGEX.search(comment)
    tadv_match = TADV_REGEX.search(comment)

    adv = float(adv_match.group(1)) if adv_match else None
    tadv = float(tadv_match.group(1)) if tadv_match else None
    return adv, tadv


def collect_candidates(node: chess.pgn.GameNode, board: chess.Board) -> list[Candidate]:
    candidates: list[Candidate] = []
    for idx, child in enumerate(node.variations):
        san = board.san(child.move)
        adv, tadv = parse_advantages(child.comment)
        candidates.append(Candidate(idx=idx, san=san, adv=adv, tadv=tadv, node=child))
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
    game: chess.pgn.Game, repertoire_color: chess.Color
) -> list[GapRecord]:
    board = game.board()
    line: list[str] = []
    records: list[GapRecord] = []

    def walk(node: chess.pgn.GameNode) -> None:
        if board.turn == repertoire_color and node.variations:
            candidates = collect_candidates(node, board)
            if len(candidates) >= 2:
                best_immediate = best_candidate(
                    candidates,
                    lambda c: (
                        c.adv if c.adv is not None else float("-inf"),
                        -c.idx,
                    ),
                )

                terminal_candidates = [c for c in candidates if c.tadv is not None]
                best_terminal = (
                    best_candidate(
                        terminal_candidates,
                        lambda c: (
                            c.tadv if c.tadv is not None else float("-inf"),
                            -c.idx,
                        ),
                    )
                    if terminal_candidates
                    else None
                )

                if (
                    best_terminal
                    and best_immediate
                    and best_terminal.idx != best_immediate.idx
                    and best_terminal.adv is not None
                    and best_immediate.adv is not None
                    and best_terminal.tadv is not None
                    and best_immediate.tadv is not None
                ):
                    gap = best_immediate.adv - best_terminal.adv
                    if gap > 0:
                        records.append(
                            GapRecord(
                                line=list(line),
                                fen=board.fen(),
                                terminal=best_terminal,
                                immediate=best_immediate,
                                gap=gap,
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
            "Identify positions where the terminal-best move had a worse "
            "immediate advantage than the chosen move."
        )
    )
    parser.add_argument("pgn", help="Repertoire PGN to analyze")
    parser.add_argument(
        "--player-side",
        choices=["auto", "white", "black"],
        default="auto",
        help="Repertoire side (default: auto via RepertoireSide header)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of largest gaps to display",
    )

    args = parser.parse_args()

    path = Path(args.pgn)
    if not path.exists():
        parser.error(f"PGN not found: {path}")

    all_records: list[GapRecord] = []
    with path.open() as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            color = determine_player_color(game, args.player_side)
            all_records.extend(analyze_game(game, color))

    if not all_records:
        print("No positions had terminal-best moves with lower immediate advantage.")
        return 0

    all_records.sort(key=lambda r: r.gap, reverse=True)

    print(f"Positions with conflicting best moves: {len(all_records)}")
    print(f"Largest required tolerance: {all_records[0].gap:.2f}")

    print()
    for record in all_records[: args.limit]:
        print(f"Line: {format_line(record.line)}")
        terminal_adv = format_value(record.terminal.adv)
        terminal_tadv = format_value(record.terminal.tadv)
        print(
            f"  Terminal winner: {record.terminal.san} "
            f"(A {terminal_adv}, TS {terminal_tadv})"
        )
        immediate_adv = format_value(record.immediate.adv)
        immediate_tadv = format_value(record.immediate.tadv)
        print(
            f"  Immediate winner: {record.immediate.san} "
            f"(A {immediate_adv}, TS {immediate_tadv})"
        )
        print(f"  Advantage gap (tolerance needed): {record.gap:.2f}")
        print(f"  FEN: {record.fen}")
        print("---")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Analyze repertoire PGNs to find positions where the move with the highest
immediate advantage differs from the move with the highest terminal advantage.

When requested, only consider differences where the immediate-advantage move
is popular enough (>= min_advantage_baseline_popularity).
"""

from __future__ import annotations

import argparse
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import chess
import chess.pgn

from cache import ChessCache
from config import Config

ADV_PATTERN = re.compile(r"Adv:\s*([+-]?\d+(?:\.\d+)?)")
TADV_PATTERN = re.compile(r"TAdv:\s*([+-]?\d+(?:\.\d+)?)")


@dataclass
class MoveInfo:
    node: chess.pgn.ChildNode
    san: str
    uci: str
    adv: float | None
    tadv: float | None
    raw_games: int | None = None
    popularity: float | None = None


@dataclass
class DifferenceRecord:
    path: str
    adv_move_san: str
    adv_adv: float
    adv_tadv: float | None
    tadv_move_san: str
    tadv_adv: float
    tadv_tadv: float | None
    difference: float
    adv_popularity: float | None = None
    tadv_popularity: float | None = None


@dataclass
class AnalysisResult:
    records: list[DifferenceRecord]
    positions_with_stats: int
    positions_same_choice: int
    positions_filtered_by_baseline: int = 0
    positions_missing_popularity: int = 0


@dataclass
class AnalysisSettings:
    baseline_threshold: float | None = None
    apply_baseline_filter: bool = False
    popularity_provider: "MovePopularityProvider | None" = None


class MovePopularityProvider:
    """Fetch move popularity data from the local cache."""

    def __init__(
        self,
        cache_path: Path,
        ratings: list[int],
        time_controls: list[str],
    ):
        self.cache = ChessCache(str(cache_path))
        self.ratings = ratings
        self.time_controls = time_controls
        self._fen_cache: dict[str, dict[str, int]] = {}

    def get_move_totals(self, fen: str) -> dict[str, int]:
        if fen in self._fen_cache:
            return self._fen_cache[fen]

        data = self.cache.get_lichess_stats(fen, self.ratings, self.time_controls)
        totals: dict[str, int] = {}
        if data and data.get("moves"):
            for move in data["moves"]:
                uci = move.get("uci")
                if not uci:
                    continue
                total = int(
                    move.get("white", 0) + move.get("draws", 0) + move.get("black", 0)
                )
                totals[uci] = total

        self._fen_cache[fen] = totals
        return totals


def parse_annotations(comment: str | None) -> tuple[float | None, float | None]:
    """Extract Adv and TAdv floats from the PGN comment string."""
    if not comment:
        return None, None
    adv = ADV_PATTERN.search(comment)
    tadv = TADV_PATTERN.search(comment)
    adv_val = float(adv.group(1)) if adv else None
    tadv_val = float(tadv.group(1)) if tadv else None
    return adv_val, tadv_val


def percentile(sorted_values: list[float], pct: float) -> float:
    """Compute percentile with linear interpolation (pct in [0, 1])."""
    if not sorted_values:
        raise ValueError("Cannot compute percentile of empty data.")
    if pct <= 0:
        return sorted_values[0]
    if pct >= 1:
        return sorted_values[-1]
    position = pct * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[int(position)]
    fraction = position - lower
    return (
        sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction
    )


def determine_side(game: chess.pgn.Game, requested: str) -> chess.Color:
    """Resolve which side represents the repertoire player."""
    if requested != "auto":
        side = requested
    else:
        header_side = game.headers.get("RepertoireSide", "").strip().lower()
        side = header_side if header_side in {"white", "black"} else "white"
    return chess.WHITE if side == "white" else chess.BLACK


def collect_differences(
    game: chess.pgn.Game,
    player_color: chess.Color,
    settings: AnalysisSettings,
) -> AnalysisResult:
    records: list[DifferenceRecord] = []
    positions_with_stats = 0
    positions_same_choice = 0
    positions_filtered_by_baseline = 0
    positions_missing_popularity = 0

    def walk(node: chess.pgn.GameNode, path: list[str]) -> None:
        nonlocal positions_with_stats, positions_same_choice
        nonlocal positions_filtered_by_baseline, positions_missing_popularity
        board = node.board()
        is_player_turn = board.turn == player_color
        popularity_totals = (
            settings.popularity_provider.get_move_totals(board.fen())
            if settings.popularity_provider and is_player_turn
            else None
        )

        children: list[MoveInfo] = []
        for child in node.variations:
            san = board.san(child.move)
            uci = child.move.uci()
            adv, tadv = parse_annotations(child.comment)
            raw_games = popularity_totals.get(uci) if popularity_totals else None
            children.append(
                MoveInfo(
                    node=child,
                    san=san,
                    uci=uci,
                    adv=adv,
                    tadv=tadv,
                    raw_games=raw_games,
                )
            )

        if popularity_totals:
            total_known_games = sum(
                child.raw_games for child in children if child.raw_games is not None
            )
            if total_known_games > 0:
                for child in children:
                    if child.raw_games is not None:
                        child.popularity = child.raw_games / total_known_games

        if is_player_turn:
            adv_children = [c for c in children if c.adv is not None]
            tadv_children = [c for c in children if c.tadv is not None]
            if adv_children and tadv_children:
                positions_with_stats += 1
                best_adv = max(adv_children, key=lambda c: (c.adv, c.san))
                best_tadv = max(tadv_children, key=lambda c: (c.tadv, c.san))
                if best_adv.san == best_tadv.san:
                    positions_same_choice += 1
                else:
                    adv_value = best_adv.adv
                    tadv_adv_value = best_tadv.adv
                    if adv_value is not None and tadv_adv_value is not None:
                        should_record = True
                        if (
                            settings.apply_baseline_filter
                            and settings.baseline_threshold is not None
                        ):
                            popularity = best_adv.popularity
                            if popularity is None:
                                positions_missing_popularity += 1
                                should_record = False
                            elif popularity < settings.baseline_threshold:
                                positions_filtered_by_baseline += 1
                                should_record = False
                        if should_record:
                            records.append(
                                DifferenceRecord(
                                    path=" ".join(path) if path else "(root)",
                                    adv_move_san=best_adv.san,
                                    adv_adv=adv_value,
                                    adv_tadv=best_adv.tadv,
                                    tadv_move_san=best_tadv.san,
                                    tadv_adv=tadv_adv_value,
                                    tadv_tadv=best_tadv.tadv,
                                    difference=adv_value - tadv_adv_value,
                                    adv_popularity=best_adv.popularity,
                                    tadv_popularity=best_tadv.popularity,
                                )
                            )

        for child_info in children:
            walk(child_info.node, path + [child_info.san])

    walk(game, [])
    return AnalysisResult(
        records=records,
        positions_with_stats=positions_with_stats,
        positions_same_choice=positions_same_choice,
        positions_filtered_by_baseline=positions_filtered_by_baseline,
        positions_missing_popularity=positions_missing_popularity,
    )


def analyze_games(
    games: Iterable[chess.pgn.Game],
    side: str,
    settings: AnalysisSettings,
) -> AnalysisResult:
    all_records: list[DifferenceRecord] = []
    total_positions_with_stats = 0
    total_positions_same_choice = 0
    total_positions_filtered_by_baseline = 0
    total_positions_missing_popularity = 0

    for game in games:
        if game is None:
            continue
        player_color = determine_side(game, side)
        result = collect_differences(game, player_color, settings)
        all_records.extend(result.records)
        total_positions_with_stats += result.positions_with_stats
        total_positions_same_choice += result.positions_same_choice
        total_positions_filtered_by_baseline += result.positions_filtered_by_baseline
        total_positions_missing_popularity += result.positions_missing_popularity

    return AnalysisResult(
        records=all_records,
        positions_with_stats=total_positions_with_stats,
        positions_same_choice=total_positions_same_choice,
        positions_filtered_by_baseline=total_positions_filtered_by_baseline,
        positions_missing_popularity=total_positions_missing_popularity,
    )


def load_games(path: Path) -> list[chess.pgn.Game]:
    games: list[chess.pgn.Game] = []
    with path.open("r", encoding="utf-8") as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            games.append(game)
    return games


def _format_pop(value: float | None) -> str:
    if value is None:
        return ""
    return f", Pop {value * 100:.2f}%"


def print_record(record: DifferenceRecord) -> None:
    print(record.path)
    print(
        f"  Adv-best:  {record.adv_move_san} "
        f"(Adv {record.adv_adv:.2f}, TAdv {record.adv_tadv if record.adv_tadv is not None else '—'}"
        f"{_format_pop(record.adv_popularity)})"
    )
    print(
        f"  TAdv-best: {record.tadv_move_san} "
        f"(Adv {record.tadv_adv:.2f}, TAdv {record.tadv_tadv if record.tadv_tadv is not None else '—'}"
        f"{_format_pop(record.tadv_popularity)})"
    )
    print(f"  Difference: {record.difference:.2f}\n")


def summarize(records: list[DifferenceRecord]) -> None:
    if not records:
        print("No positions found where Adv-best and TAdv-best moves differ.")
        return

    differences = sorted(r.difference for r in records)

    def fmt(value: float) -> str:
        return f"{value:.2f}"

    mean = statistics.mean(differences)
    median = statistics.median(differences)
    stdev = statistics.pstdev(differences) if len(differences) > 1 else 0.0

    print("Difference distribution (Adv(best) - Adv(terminal-best))")
    print(f"  Count: {len(differences)}")
    print(f"  Min / Max: {fmt(differences[0])} / {fmt(differences[-1])}")
    print(f"  Mean / Median: {fmt(mean)} / {fmt(median)}")
    print(f"  Std Dev: {fmt(stdev)}")
    print(
        f"  25th / 75th percentiles: "
        f"{fmt(percentile(differences, 0.25))} / {fmt(percentile(differences, 0.75))}"
    )
    print(
        f"  90th / 95th percentiles: "
        f"{fmt(percentile(differences, 0.90))} / {fmt(percentile(differences, 0.95))}"
    )
    print()


def explain_summary(result: AnalysisResult, threshold: float | None) -> None:
    print("Player-move coverage:")
    print(f"  Positions analyzed: {result.positions_with_stats}")
    print(f"  Same best move: {result.positions_same_choice}")
    different = result.positions_with_stats - result.positions_same_choice
    print(f"  Different best move: {different}")
    if threshold is not None:
        print(f"  Baseline threshold: {threshold:.2f}")
    if result.positions_filtered_by_baseline:
        print(f"  Skipped (below threshold): {result.positions_filtered_by_baseline}")
    if result.positions_missing_popularity:
        print(
            f"  Skipped (missing popularity data): {result.positions_missing_popularity}"
        )
    print(f"  Included in statistics: {len(result.records)}")
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare immediate vs terminal advantages in repertoire PGNs."
    )
    parser.add_argument(
        "--pgn",
        type=Path,
        default=Path("repertoire_white.pgn"),
        help="Path to the repertoire PGN.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration file (for thresholds and cache settings).",
    )
    parser.add_argument(
        "--side",
        choices=["white", "black", "auto"],
        default="auto",
        help="Which side represents the repertoire player (default: auto from PGN tag, fallback white).",
    )
    parser.add_argument(
        "--baseline-threshold",
        type=float,
        help="Override min_advantage_baseline_popularity (0-1).",
    )
    parser.add_argument(
        "--no-baseline-filter",
        action="store_true",
        help="Do not require the Adv-best move to clear the baseline popularity threshold.",
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        help="Override cache file path (defaults to config cache_file).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Show the top N differences (default: 10).",
    )
    parser.add_argument(
        "--smallest",
        type=int,
        default=5,
        help="Show the smallest N differences (default: 5).",
    )
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="Print every differing position instead of just summaries/top results.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    games = load_games(args.pgn)
    if not games:
        print(f"No games found in {args.pgn}")
        return 1

    config = Config.from_yaml(str(args.config))
    baseline_threshold = (
        args.baseline_threshold
        if args.baseline_threshold is not None
        else config.min_advantage_baseline_popularity
    )
    cache_file = Path(args.cache_file) if args.cache_file else Path(config.cache_file)
    apply_baseline_filter = (
        not args.no_baseline_filter and baseline_threshold is not None
    )

    popularity_provider = (
        MovePopularityProvider(
            cache_file,
            config.ratings,
            config.time_control,
        )
        if apply_baseline_filter
        else None
    )

    settings = AnalysisSettings(
        baseline_threshold=baseline_threshold if apply_baseline_filter else None,
        apply_baseline_filter=apply_baseline_filter,
        popularity_provider=popularity_provider,
    )

    result = analyze_games(games, args.side, settings)
    explain_summary(result, settings.baseline_threshold)

    differing_records = result.records
    summarize(differing_records)

    if args.list_all:
        print("All differing positions:\n")
        for record in differing_records:
            print_record(record)
    else:
        if args.top > 0:
            print(f"Top {args.top} differences:\n")
            for record in sorted(
                differing_records, key=lambda r: r.difference, reverse=True
            )[: args.top]:
                print_record(record)
        if args.smallest > 0:
            print(f"Smallest {args.smallest} differences:\n")
            for record in sorted(differing_records, key=lambda r: r.difference)[
                : args.smallest
            ]:
                print_record(record)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

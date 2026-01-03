from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass, field

import yaml


@dataclass
class Config:
    initial_moves_white: list[str] = field(default_factory=lambda: ["e4"])
    initial_moves_black: list[str] = field(default_factory=lambda: ["e4 d5"])
    time_control: list[str] = field(default_factory=lambda: ["rapid", "blitz"])
    ratings: list[int] = field(default_factory=lambda: [1600, 1800, 2000, 2200, 2500])
    min_opponent_popularity: float = 0.1
    # Popularity threshold for player moves using master reference data
    min_highrating_popularity: float = 0.1
    # Allow alternative player moves whose advantage is close to the best move
    advantage_tolerance: float = 0.02
    # Method to aggregate move advantages when combining explorer data
    advantage_aggregation: str = "median"
    # Minimum popularity (relative) for a move to be considered as baseline for advantage comparison
    min_advantage_baseline_popularity: float = 0.1
    min_lichess_games: int = 1000  # Minimum Lichess games to continue exploring
    output_file: str = "repertoire.pgn"
    cache_file: str = "chess_cache.db"
    master_cache_file: str = "master_cache.db"
    stockfish_cache_file: str = "stockfish_cache.db"
    use_proxy: bool = True  # Enable/disable HTTP proxies for Lichess API calls
    opponent_fallback_count: int = (
        1  # Minimum opponent continuations when popularity threshold fails
    )
    prune_non_best_moves: bool = False  # Prune non-best player moves after evaluation
    use_stockfish: bool = False  # Whether to use Stockfish evaluation
    stockfish_path: str = "stockfish"  # Path to Stockfish executable
    stockfish_depth: int = 15  # Stockfish search depth
    stockfish_threads: int = 4  # Number of Stockfish threads
    terminal_advantage_weight: float = (
        0.5  # Weight for terminal advantage in terminal score
    )
    stockfish_score_weight: float = 0.5  # Weight for Stockfish score in terminal score

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Config":
        config = cls()
        if os.path.exists(yaml_path):
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    key_map = {
                        "min_master_popularity": "min_highrating_popularity",
                    }
                    for key, value in data.items():
                        mapped_key = key_map.get(key, key)
                        if mapped_key != key:
                            key = mapped_key
                        if hasattr(config, key):
                            setattr(config, key, value)
        return config

    def apply_cli_args(self, args: argparse.Namespace) -> None:
        for key, value in vars(args).items():
            if value is not None and hasattr(self, key):
                setattr(self, key, value)

    def validate(self) -> None:
        if not 0 <= self.min_opponent_popularity <= 1:
            raise ValueError("min_opponent_popularity must be between 0 and 1")

        if not 0 <= self.min_highrating_popularity <= 1:
            raise ValueError("min_highrating_popularity must be between 0 and 1")

        if not 0 <= self.advantage_tolerance <= 1:
            raise ValueError("advantage_tolerance must be between 0 and 1")

        if not 0 <= self.min_advantage_baseline_popularity <= 1:
            raise ValueError(
                "min_advantage_baseline_popularity must be between 0 and 1"
            )

        agg_method = str(getattr(self, "advantage_aggregation", "median")).lower()
        if agg_method not in {"mean", "median"}:
            raise ValueError("advantage_aggregation must be either 'mean' or 'median'")
        self.advantage_aggregation = agg_method

        if not 0 <= self.terminal_advantage_weight <= 1:
            raise ValueError("terminal_advantage_weight must be between 0 and 1")

        if not 0 <= self.stockfish_score_weight <= 1:
            raise ValueError("stockfish_score_weight must be between 0 and 1")

        total_weight = self.terminal_advantage_weight + self.stockfish_score_weight
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(
                f"terminal_advantage_weight + stockfish_score_weight must equal 1.0 (got {total_weight})"
            )

        if self.stockfish_depth < 0:
            raise ValueError("stockfish_depth must be non-negative")

        if self.stockfish_threads < 0:
            raise ValueError("stockfish_threads must be non-negative")

        valid_time_controls = [
            "ultraBullet",
            "bullet",
            "blitz",
            "rapid",
            "classical",
            "correspondence",
        ]
        for tc in self.time_control:
            if tc not in valid_time_controls:
                raise ValueError(
                    f"Invalid time control: {tc}. Must be one of {valid_time_controls}"
                )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate chess repertoire from Lichess data"
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--initial-moves-white",
        type=str,
        nargs="+",
        help="Initial moves for white repertoire (e.g., e2e4 e7e5)",
    )

    parser.add_argument(
        "--initial-moves-black",
        type=str,
        nargs="+",
        help="Initial moves for black repertoire (e.g., e2e4 e7e5)",
    )

    parser.add_argument(
        "--time-control", type=str, nargs="+", help="Time controls to consider"
    )

    parser.add_argument(
        "--ratings",
        type=int,
        nargs="+",
        help="Rating bracket lower bounds for Lichess explorer (e.g. 1600 1800 2000)",
    )

    parser.add_argument(
        "--min-popularity",
        type=float,
        help="Minimum popularity for opponent moves (0-1)",
    )

    parser.add_argument(
        "--min-highrating-popularity",
        type=float,
        help="Minimum popularity for player moves in master reference games (0-1)",
    )

    parser.add_argument(
        "--advantage-tolerance",
        type=float,
        help="Allow alternative player moves within this advantage of the best move (0-1)",
    )

    parser.add_argument(
        "--advantage-aggregation",
        choices=["median", "mean"],
        help="Choose how move advantages are aggregated when evaluating positions",
    )

    parser.add_argument(
        "--min-advantage-baseline-popularity",
        type=float,
        help="Minimum popularity (relative, 0-1) for a move to be used as baseline for advantage comparison",
    )

    # Backward compatibility for legacy flags
    parser.add_argument(
        "--min-master-popularity",
        type=float,
        dest="min_highrating_popularity",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--output", type=str, dest="output_file", help="Output PGN file path"
    )

    parser.add_argument(
        "--cache", type=str, dest="cache_file", help="Cache database file path"
    )

    parser.add_argument(
        "--master-cache",
        type=str,
        dest="master_cache_file",
        help="Master games cache database file path",
    )

    parser.add_argument(
        "--stockfish-cache",
        type=str,
        dest="stockfish_cache_file",
        help="Stockfish evaluation cache database file path",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )

    parser.add_argument(
        "--use-proxy",
        dest="use_proxy",
        action="store_true",
        help="Enable HTTP proxies when contacting Lichess (default: True)",
    )

    parser.add_argument(
        "--no-use-proxy",
        dest="use_proxy",
        action="store_false",
        help="Disable HTTP proxies when contacting Lichess",
    )

    parser.add_argument(
        "--prune-non-best-moves",
        dest="prune_non_best_moves",
        action="store_true",
        help="Prune non-best player moves after terminal advantages are computed",
    )

    parser.add_argument(
        "--no-prune-non-best-moves",
        dest="prune_non_best_moves",
        action="store_false",
        help="Keep all player moves even if they are suboptimal",
    )

    parser.set_defaults(use_proxy=None, prune_non_best_moves=None)

    return parser.parse_args()


def load_config(args: argparse.Namespace | None = None) -> Config:
    if args is None:
        args = parse_arguments()
    config = Config.from_yaml(args.config)
    config.apply_cli_args(args)

    config.validate()
    return config


@dataclass
class PostprocessConfig:
    """Configuration for PGN postprocessing."""

    input_file: str = ""
    initial_lines: list[str] = field(default_factory=list)
    max_depth: int | None = None
    min_games: int = 0
    # Granular comment removal options
    remove_advantage: bool = False  # Remove A: field
    remove_terminal_advantage: bool = False  # Remove T: field
    remove_popularity: bool = False  # Remove P: field
    remove_game_count: bool = False  # Remove G: field
    remove_alternatives: bool = False  # Remove Alts: field
    # Move annotation glyphs (NAGs) options
    add_move_indicators: bool = False  # Enable opponent move indicators
    good_threshold: float = 0.05  # ! delta threshold
    inaccuracy_threshold: float = -0.05  # ?! delta threshold
    mistake_threshold: float = -0.10  # ? delta threshold
    blunder_threshold: float = -0.15  # ?? delta threshold
    use_nag_codes: bool = False  # Use $N codes instead of symbols

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "PostprocessConfig":
        config = cls()
        if os.path.exists(yaml_path):
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    key_map = {
                        "postprune_max_depth": "max_depth",
                        "postprune_min_games": "min_games",
                    }
                    for key, value in data.items():
                        mapped_key = key_map.get(key, key)
                        if hasattr(config, mapped_key):
                            setattr(config, mapped_key, value)
        return config

    def apply_cli_args(self, args: argparse.Namespace) -> None:
        for key, value in vars(args).items():
            if value is not None and hasattr(self, key):
                setattr(self, key, value)

    def validate(self) -> None:
        # Normalize initial lines into a list of strings
        if self.initial_lines is None:
            self.initial_lines = []
        elif isinstance(self.initial_lines, str):
            split_values = [
                part for part in re.split(r"[;,]", self.initial_lines) if part.strip()
            ]
            self.initial_lines = split_values or [self.initial_lines]
        elif not isinstance(self.initial_lines, list):
            raise ValueError("initial_lines must be a string or list of strings")

        normalized_moves = []
        for moves in self.initial_lines:
            if not isinstance(moves, str):
                raise ValueError("initial_lines must contain only strings")
            cleaned = " ".join(moves.split())
            if cleaned:
                normalized_moves.append(cleaned)
        self.initial_lines = normalized_moves

        if not self.input_file:
            raise ValueError("Input file is required")
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must be non-negative when set")
        if self.min_games < 0:
            raise ValueError("min_games must be non-negative")


def parse_postprocess_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Postprocess PGN repertoire files (remove comments, prune variations)"
    )

    parser.add_argument(
        "--config",
        type=str,
        default="postprocess.yaml",
        help="Path to YAML configuration file",
    )

    parser.add_argument(
        "--input",
        type=str,
        dest="input_file",
        help="Input PGN file path",
    )

    parser.add_argument(
        "--initial-lines",
        type=str,
        nargs="+",
        dest="initial_lines",
        default=None,
        help="Filter to specific initial move sequences; multiple entries produce separate files",
    )

    parser.add_argument(
        "--max-depth",
        type=int,
        dest="max_depth",
        default=None,
        help="Maximum player-move depth to keep (None to disable)",
    )

    parser.add_argument(
        "--min-games",
        type=int,
        dest="min_games",
        default=None,
        help="Minimum total games required to keep a position",
    )

    # Backward compatibility for legacy postprocess flags
    parser.add_argument(
        "--postprune-max-depth",
        type=int,
        dest="max_depth",
        default=None,
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--postprune-min-games",
        type=int,
        dest="min_games",
        default=None,
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--remove-advantage",
        action="store_true",
        default=None,
        help="Remove advantage (A:) field from comments",
    )

    parser.add_argument(
        "--remove-terminal-advantage",
        action="store_true",
        default=None,
        help="Remove terminal advantage (T:) field from comments",
    )

    parser.add_argument(
        "--remove-popularity",
        action="store_true",
        default=None,
        help="Remove popularity (P:) field from comments",
    )

    parser.add_argument(
        "--remove-game-count",
        action="store_true",
        default=None,
        help="Remove game count (G:) field from comments",
    )

    parser.add_argument(
        "--remove-alternatives",
        action="store_true",
        default=None,
        help="Remove alternatives (Alts:) field from comments",
    )

    parser.add_argument(
        "--add-move-indicators",
        action="store_true",
        default=None,
        help="Add opponent move indicators based on terminal advantage deltas",
    )

    parser.add_argument(
        "--good-threshold",
        type=float,
        default=None,
        help="Delta threshold for good move (default: 0.05)",
    )

    parser.add_argument(
        "--inaccuracy-threshold",
        type=float,
        default=None,
        help="Delta threshold for inaccuracy (default: -0.05)",
    )

    parser.add_argument(
        "--mistake-threshold",
        type=float,
        default=None,
        help="Delta threshold for mistake (default: -0.10)",
    )

    parser.add_argument(
        "--blunder-threshold",
        type=float,
        default=None,
        help="Delta threshold for blunder (default: -0.15)",
    )

    parser.add_argument(
        "--use-nag-codes",
        action="store_true",
        default=None,
        help="Use numeric annotation codes ($1, $2, etc.) instead of symbols (!, ?, etc.)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )

    return parser.parse_args()


def load_postprocess_config(
    args: argparse.Namespace | None = None,
) -> PostprocessConfig:
    if args is None:
        args = parse_postprocess_arguments()

    config = PostprocessConfig.from_yaml(args.config)
    config.apply_cli_args(args)
    config.validate()
    return config

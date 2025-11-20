from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field

import yaml


@dataclass
class Config:
    initial_moves_white: list[str] = field(default_factory=lambda: ["e4"])
    initial_moves_black: list[str] = field(default_factory=lambda: ["e4 d5"])
    time_control: list[str] = field(default_factory=lambda: ["rapid", "blitz"])
    depth: int = 10  # Maximum player moves to explore after initial moves
    ratings: list[int] = field(default_factory=lambda: [1600, 1800, 2000, 2200, 2500])
    min_opponent_popularity: float = 0.1
    # Popularity threshold for player moves using master (or fallback) reference data
    min_highrating_popularity: float = 0.1
    # Allow alternative player moves whose advantage is close to the best move
    advantage_tolerance: float = 0.02
    # Method to aggregate move advantages when combining explorer data
    advantage_aggregation: str = "median"
    # Minimum popularity (relative) for a move to be considered as baseline for advantage comparison
    min_advantage_baseline_popularity: float = 0.1
    # Minimum master games required before falling back to high-rating Explorer data
    min_highrating_games: int = 200
    min_lichess_games: int = 1000  # Minimum Lichess games to continue exploring
    postprune_min_lichess_games: int = (
        0  # Minimum Lichess games to keep a move after building the tree
    )
    postprune_depth: int | None = None  # Maximum player depth to keep after pruning
    highrating_fallback: bool = True  # Whether to fall back to high-rating data when master games are insufficient
    output_file: str = "repertoire.pgn"
    cache_file: str = "chess_cache.db"
    include_comments: bool = True  # Toggle for PGN comments
    use_proxy: bool = True  # Enable/disable HTTP proxies for Lichess API calls
    side: str | None = None  # Active side during analysis (set at runtime)
    opponent_fallback_count: int = (
        1  # Minimum opponent continuations when popularity threshold fails
    )
    prune_non_best_moves: bool = False  # Prune non-best player moves after evaluation

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Config":
        config = cls()
        if os.path.exists(yaml_path):
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    key_map = {
                        "min_master_popularity": "min_highrating_popularity",
                        "min_master_games": "min_highrating_games",
                        "postprune_min_licess_games": "postprune_min_lichess_games",
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
        if self.depth < 1 or self.depth > 50:
            raise ValueError(
                "Depth must be between 1 and 50 (represents player moves after initial position)"
            )

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

        if self.min_highrating_games < 0:
            raise ValueError("min_highrating_games must be non-negative")

        if self.postprune_min_lichess_games < 0:
            raise ValueError("postprune_min_lichess_games must be non-negative")

        if self.postprune_depth is not None and self.postprune_depth < 0:
            raise ValueError("postprune_depth must be non-negative")

        agg_method = str(getattr(self, "advantage_aggregation", "median")).lower()
        if agg_method not in {"mean", "median"}:
            raise ValueError("advantage_aggregation must be either 'mean' or 'median'")
        self.advantage_aggregation = agg_method

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
        "--depth",
        type=int,
        help="Maximum player moves to explore after initial moves (depth in terms of player moves)",
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
        help="Minimum popularity for player moves in master/high-rating reference games (0-1, used only when highrating_fallback is enabled)",
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

    parser.add_argument(
        "--min-highrating-games",
        type=int,
        help="Minimum master games required (if highrating_fallback is enabled, falls back to high-rating data below this threshold)",
    )
    parser.add_argument(
        "--postprune-min-lichess-games",
        type=int,
        help="Minimum Lichess games required to keep a move after repertoire generation",
    )

    parser.add_argument(
        "--postprune-depth",
        type=int,
        help="Maximum player depth to keep when post-pruning the repertoire",
    )

    parser.add_argument(
        "--highrating-fallback",
        dest="highrating_fallback",
        action="store_true",
        help="Enable fallback to high-rating data when master games are insufficient (default: True)",
    )

    parser.add_argument(
        "--no-highrating-fallback",
        dest="highrating_fallback",
        action="store_false",
        help="Disable fallback to high-rating data when master games are insufficient",
    )

    # Backward compatibility for legacy flags
    parser.add_argument(
        "--min-master-popularity",
        type=float,
        dest="min_highrating_popularity",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--min-master-games",
        type=int,
        dest="min_highrating_games",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--output", type=str, dest="output_file", help="Output PGN file path"
    )

    parser.add_argument(
        "--cache", type=str, dest="cache_file", help="Cache database file path"
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

    parser.add_argument(
        "--postprune-min-licess-games",
        type=int,
        dest="postprune_min_lichess_games",
        help=argparse.SUPPRESS,
    )

    parser.set_defaults(
        use_proxy=None, prune_non_best_moves=None, highrating_fallback=True
    )

    return parser.parse_args()


def load_config(args: argparse.Namespace | None = None) -> Config:
    if args is None:
        args = parse_arguments()
    config = Config.from_yaml(args.config)
    config.apply_cli_args(args)

    config.validate()
    return config

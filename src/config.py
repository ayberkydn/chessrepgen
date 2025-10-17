import argparse
import yaml
import os
from typing import Any
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    initial_moves_white: list[str] = field(default_factory=lambda: ["e4"])
    initial_moves_black: list[str] = field(default_factory=lambda: ["e4 d5"])
    time_control: list[str] = field(default_factory=lambda: ["rapid", "blitz"])
    depth: int = 10  # Maximum player moves to explore after initial moves
    min_rating: int = 1600
    max_rating: int = 2200
    min_popularity: float = 0.1
    min_master_popularity: float = 0.1
    min_master_games: int = 200
    min_lichess_games: int = 1000  # Minimum Lichess games to continue exploring
    output_file: str = "repertoire.pgn"
    cache_file: str = "chess_cache.db"
    include_comments: bool = True  # Toggle for PGN comments
    side: str | None = None  # Active side during analysis (set at runtime)
    # Winrate tolerance for selecting multiple moves
    winrate_tolerance: float = 0.05  # 5% tolerance from best move's winrate
    # Analysis settings
    # Alternative move analysis is always enabled
    # Stockfish settings
    use_stockfish: bool = True  # Enable/disable Stockfish for move selection fallback and terminal node evaluation
    stockfish_path: str | None = None  # Auto-detect if None
    stockfish_depth: int = 15
    stockfish_threshold: float = (
        0.05  # 5 centipawns from best move (for move selection)
    )
    stockfish_advantage_threshold: float = 1.0  # Terminate if player is ahead by this many pawns (works independently of use_stockfish)
    # Master game augmentation settings
    augment_master_games: bool = (
        True  # Augment master games with high-rated Lichess games
    )
    augment_min_rating: int = 2200  # Minimum rating for augmentation games
    augment_time_controls: list[str] = field(
        default_factory=lambda: ["classical", "rapid"]
    )  # Time controls for augmentation

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Config":
        config = cls()
        if os.path.exists(yaml_path):
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    for key, value in data.items():
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

        if self.min_rating >= self.max_rating:
            raise ValueError("min_rating must be less than max_rating")

        if not 0 <= self.min_popularity <= 1:
            raise ValueError("min_popularity must be between 0 and 1")

        if not 0 <= self.min_master_popularity <= 1:
            raise ValueError("min_master_popularity must be between 0 and 1")

        if self.min_master_games < 0:
            raise ValueError("min_master_games must be non-negative")

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

        # Validate winrate_tolerance
        if not 0 <= self.winrate_tolerance <= 1:
            raise ValueError("winrate_tolerance must be between 0 and 1")

        if hasattr(self, "augment_time_controls"):
            for tc in self.augment_time_controls:
                if tc not in valid_time_controls:
                    raise ValueError(
                        f"Invalid augmentation time control: {tc}. Must be one of {valid_time_controls}"
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
        "--min-rating", type=int, help="Minimum rating for Lichess games"
    )

    parser.add_argument(
        "--max-rating", type=int, help="Maximum rating for Lichess games"
    )

    parser.add_argument(
        "--min-popularity",
        type=float,
        help="Minimum popularity for opponent moves (0-1)",
    )

    parser.add_argument(
        "--min-master-popularity",
        type=float,
        help="Minimum popularity for player moves in master games (0-1)",
    )

    parser.add_argument(
        "--min-master-games",
        type=int,
        help="Minimum number of master games to continue exploring a position",
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
        "--stockfish-advantage-threshold",
        type=float,
        dest="stockfish_advantage_threshold",
        help="Terminate branch if Stockfish evaluation shows player is this many pawns ahead (default: 1.0)",
    )

    parser.add_argument(
        "--winrate-tolerance",
        type=float,
        dest="winrate_tolerance",
        help="Winrate tolerance for selecting multiple moves (default: 0.05)",
    )

    return parser.parse_args()


def load_config(args: argparse.Namespace | None = None) -> Config:
    if args is None:
        args = parse_arguments()
    config = Config.from_yaml(args.config)
    config.apply_cli_args(args)

    config.validate()
    return config

import argparse
import yaml
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    side: str = "white"
    initial_moves: List[str] = field(default_factory=lambda: ["e4"])
    time_control: List[str] = field(default_factory=lambda: ["rapid", "blitz"])
    depth: int = 10
    min_rating: int = 1600
    max_rating: int = 2200
    min_popularity: float = 0.1
    min_master_popularity: float = 0.1
    min_master_games: int = 200
    output_file: str = "repertoire.pgn"
    cache_file: str = "chess_cache.db"
    cache_expiry_days: int = 30
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'Config':
        config = cls()
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r') as f:
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
        if self.side not in ["white", "black"]:
            raise ValueError("Side must be 'white' or 'black'")
        
        if self.depth < 1 or self.depth > 50:
            raise ValueError("Depth must be between 1 and 50")
        
        if self.min_rating >= self.max_rating:
            raise ValueError("min_rating must be less than max_rating")
        
        if not 0 <= self.min_popularity <= 1:
            raise ValueError("min_popularity must be between 0 and 1")
        
        if not 0 <= self.min_master_popularity <= 1:
            raise ValueError("min_master_popularity must be between 0 and 1")
        
        if self.min_master_games < 0:
            raise ValueError("min_master_games must be non-negative")
        
        valid_time_controls = ["ultraBullet", "bullet", "blitz", "rapid", "classical", "correspondence"]
        for tc in self.time_control:
            if tc not in valid_time_controls:
                raise ValueError(f"Invalid time control: {tc}. Must be one of {valid_time_controls}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate chess repertoire from Lichess data"
    )
    
    parser.add_argument(
        "--config", 
        type=str, 
        default="config.yaml",
        help="Path to YAML configuration file"
    )
    
    parser.add_argument(
        "--side", 
        type=str, 
        choices=["white", "black"],
        help="Side to generate repertoire for"
    )
    
    parser.add_argument(
        "--initial-moves",
        type=str,
        nargs="+",
        help="Initial moves in UCI format (e.g., e2e4 e7e5)"
    )
    
    parser.add_argument(
        "--time-control",
        type=str,
        nargs="+",
        help="Time controls to consider"
    )
    
    parser.add_argument(
        "--depth",
        type=int,
        help="Maximum depth of repertoire tree"
    )
    
    parser.add_argument(
        "--min-rating",
        type=int,
        help="Minimum rating for Lichess games"
    )
    
    parser.add_argument(
        "--max-rating",
        type=int,
        help="Maximum rating for Lichess games"
    )
    
    parser.add_argument(
        "--min-popularity",
        type=float,
        help="Minimum popularity for opponent moves (0-1)"
    )
    
    parser.add_argument(
        "--min-master-popularity",
        type=float,
        help="Minimum popularity for player moves in master games (0-1)"
    )
    
    parser.add_argument(
        "--min-master-games",
        type=int,
        help="Minimum number of master games to continue exploring a position"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        dest="output_file",
        help="Output PGN file path"
    )
    
    parser.add_argument(
        "--cache",
        type=str,
        dest="cache_file",
        help="Cache database file path"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output (same as --debug)"
    )
    
    return parser.parse_args()


def load_config() -> Config:
    args = parse_arguments()
    config = Config.from_yaml(args.config)
    config.apply_cli_args(args)
    config.validate()
    return config
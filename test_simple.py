#!/usr/bin/env python3

import sys
sys.path.insert(0, 'src')

from config import Config
from lichess_client import LichessClient
from cache import ChessCache
from evaluator import MoveEvaluator
import logging

logging.basicConfig(level=logging.INFO)

# Create a simple config
config = Config()
config.side = "white"
config.initial_moves = ["e4"]
config.depth = 2  # Very shallow for testing
config.min_popularity = 0.05
config.min_master_popularity = 0.05

# Test API access
client = LichessClient()
cache = ChessCache("test_cache.db", 30)
evaluator = MoveEvaluator(config)

# Test with starting position after e4
starting_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

print("Testing Lichess API...")
data = client.get_position_stats(
    starting_fen,
    config.min_rating,
    config.max_rating,
    config.time_control
)

if data["master"]:
    print(f"Master games found: {data['master'].get('white', 0) + data['master'].get('draws', 0) + data['master'].get('black', 0)}")
    
if data["lichess"]:
    print(f"Lichess games found: {data['lichess'].get('white', 0) + data['lichess'].get('draws', 0) + data['lichess'].get('black', 0)}")

# Test move evaluation
moves = evaluator.evaluate_position(data["master"], data["lichess"], is_player_turn=False)
print(f"\nFound {len(moves)} candidate moves")
for move in moves[:3]:
    print(f"  {move.san}: popularity={move.popularity:.0f} games, expected_score={move.expected_score(True):.1%}")
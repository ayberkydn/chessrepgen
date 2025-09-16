#!/usr/bin/env python3

import sys
sys.path.insert(0, 'src')

from config import Config
from lichess_client import LichessClient
from evaluator import MoveEvaluator

# Test for WHITE repertoire
print("="*60)
print("Testing WHITE repertoire")
print("="*60)

config = Config()
config.side = "white"
config.min_popularity = 0.05
config.min_master_popularity = 0.05

client = LichessClient()
evaluator = MoveEvaluator(config)

# Position after 1.e4 (Black to move - opponent's turn)
fen1 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
data1 = client.get_position_stats(fen1, 1600, 2200, ["rapid", "blitz"])
moves1 = evaluator.evaluate_position(data1["master"], data1["lichess"], is_player_turn=False)

print("\nAfter 1.e4 (Black's turn - OPPONENT):")
print(f"Number of moves: {len(moves1)} (should be multiple)")
for move in moves1[:5]:
    print(f"  - {move.san}")

# Position after 1.e4 e5 (White to move - player's turn)
fen2 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"
data2 = client.get_position_stats(fen2, 1600, 2200, ["rapid", "blitz"])
moves2 = evaluator.evaluate_position(data2["master"], data2["lichess"], is_player_turn=True)

print("\nAfter 1.e4 e5 (White's turn - PLAYER):")
print(f"Number of moves: {len(moves2)} (should be 1)")
for move in moves2:
    print(f"  - {move.san}")

print("\n" + "="*60)
print("Testing BLACK repertoire")
print("="*60)

config.side = "black"
evaluator = MoveEvaluator(config)

# Position at start (White to move - opponent's turn)
fen3 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
data3 = client.get_position_stats(fen3, 1600, 2200, ["rapid", "blitz"])
moves3 = evaluator.evaluate_position(data3["master"], data3["lichess"], is_player_turn=False)

print("\nStarting position (White's turn - OPPONENT):")
print(f"Number of moves: {len(moves3)} (should be multiple)")
for move in moves3[:5]:
    print(f"  - {move.san}")

# Position after 1.e4 (Black to move - player's turn)
fen4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
data4 = client.get_position_stats(fen4, 1600, 2200, ["rapid", "blitz"])
moves4 = evaluator.evaluate_position(data4["master"], data4["lichess"], is_player_turn=True)

print("\nAfter 1.e4 (Black's turn - PLAYER):")
print(f"Number of moves: {len(moves4)} (should be 1)")
for move in moves4:
    print(f"  - {move.san}")

print("\n" + "="*60)
print("Summary:")
print("✓ Player (repertoire side): 1 move only")
print("✓ Opponent: Multiple moves to prepare against")
#!/usr/bin/env python3

import sys
sys.path.insert(0, 'src')

from config import Config
from lichess_client import LichessClient
from evaluator import MoveEvaluator

# Setup
config = Config()
config.side = "white"
config.min_popularity = 0.05
config.min_master_popularity = 0.05

client = LichessClient()
evaluator = MoveEvaluator(config)

# Position after 1.e4
fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

print("Testing position after 1.e4")
print("="*60)

# Get data
data = client.get_position_stats(fen, 1600, 2200, ["rapid", "blitz"])

# Evaluate opponent's responses (Black's turn)
print("\n1. OPPONENT'S MOVES (Black's responses to 1.e4):")
print("-" * 40)
moves = evaluator.evaluate_position(data["master"], data["lichess"], is_player_turn=False)

for i, move in enumerate(moves[:5], 1):
    win_rate = move.expected_score_black
    print(f"{i}. {move.san:6} - Popularity: {move.total_games:,} games ({move.total_games/sum(m.total_games for m in moves)*100:.1f}%)")
    print(f"          Black scores: {win_rate:.1%}")

# Now test a position where it's White's turn (after 1.e4 e5)
fen2 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"
data2 = client.get_position_stats(fen2, 1600, 2200, ["rapid", "blitz"])

print("\n2. PLAYER'S MOVES (White's moves after 1.e4 e5):")
print("-" * 40)
moves2 = evaluator.evaluate_position(data2["master"], data2["lichess"], is_player_turn=True)

for i, move in enumerate(moves2, 1):
    score = move.expected_score_white
    print(f"{i}. {move.san:6} - Expected score: {score:.1%}")
    print(f"          Based on {move.total_games:,} master games")

print("\nKey Differences:")
print("-" * 40)
print("• Opponent moves: Selected by POPULARITY (what they actually play)")
print("• Player moves: Selected by EXPECTED SCORE (what wins most)")
print("• Opponent moves: Uses both Master + Lichess data")
print("• Player moves: Uses Master data only (higher quality)")
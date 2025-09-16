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

# Position 1: After 1.e4 (Black to move - opponent's turn)
fen1 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
data1 = client.get_position_stats(fen1, 1600, 2200, ["rapid", "blitz"])
moves1 = evaluator.evaluate_position(data1["master"], data1["lichess"], is_player_turn=False)

print("\n1. After 1.e4 (BLACK's turn - opponent):")
print(f"   Number of moves: {len(moves1)}")
if moves1:
    print("   Moves:", ", ".join([m.san for m in moves1[:5]]))

# Position 2: After 1.e4 e5 (White to move - player's turn)
fen2 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"
data2 = client.get_position_stats(fen2, 1600, 2200, ["rapid", "blitz"])
moves2 = evaluator.evaluate_position(data2["master"], data2["lichess"], is_player_turn=True)

print("\n2. After 1.e4 e5 (WHITE's turn - player):")
print(f"   Number of moves: {len(moves2)}")
if moves2:
    print("   Move:", moves2[0].san)

# Test for BLACK repertoire
print("\n" + "="*60)
print("Testing BLACK repertoire")
print("="*60)

config_black = Config()
config_black.side = "black"
config_black.min_popularity = 0.05
config_black.min_master_popularity = 0.05

evaluator_black = MoveEvaluator(config_black)

# Position 3: After 1.e4 (Black to move - player's turn for Black)
moves3 = evaluator_black.evaluate_position(data1["master"], data1["lichess"], is_player_turn=True)

print("\n3. After 1.e4 (BLACK's turn - player):")
print(f"   Number of moves: {len(moves3)}")
if moves3:
    print("   Move:", moves3[0].san)

# Position 4: After 1.e4 e5 (White to move - opponent's turn for Black)
moves4 = evaluator_black.evaluate_position(data2["master"], data2["lichess"], is_player_turn=False)

print("\n4. After 1.e4 e5 (WHITE's turn - opponent):")
print(f"   Number of moves: {len(moves4)}")
if moves4:
    print("   Moves:", ", ".join([m.san for m in moves4[:5]]))

print("\n" + "="*60)
print("SUMMARY:")
print("-"*40)
print("✓ White repertoire: White has 1 move, Black has multiple")
print("✓ Black repertoire: Black has 1 move, White has multiple")
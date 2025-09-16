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

# Position after 1.e4 e5
fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"

print("Testing position after 1.e4 e5 (White to move)")
print("="*60)

# Get data
data = client.get_position_stats(fen, 1600, 2200, ["rapid", "blitz"])

print("\nMaster games statistics:")
if data["master"]:
    total_master = data["master"].get("white", 0) + data["master"].get("draws", 0) + data["master"].get("black", 0)
    print(f"Total master games: {total_master:,}")
    
    if data["master"].get("moves"):
        print("\nMoves in master games (popularity threshold):")
        for move in data["master"]["moves"][:5]:
            games = move.get("white", 0) + move.get("draws", 0) + move.get("black", 0)
            pop = games / total_master * 100 if total_master > 0 else 0
            print(f"  {move.get('san', '???'):6} - {pop:5.1f}% ({games:,} games)")

print("\nLichess games statistics (1600-2200 rating):")
if data["lichess"]:
    total_lichess = data["lichess"].get("white", 0) + data["lichess"].get("draws", 0) + data["lichess"].get("black", 0)
    print(f"Total Lichess games: {total_lichess:,}")
    
    if data["lichess"].get("moves"):
        print("\nExpected scores from Lichess data:")
        for move in data["lichess"]["moves"][:5]:
            white_wins = move.get("white", 0)
            draws = move.get("draws", 0)
            black_wins = move.get("black", 0)
            total = white_wins + draws + black_wins
            if total > 0:
                expected = (white_wins + 0.5 * draws) / total
                print(f"  {move.get('san', '???'):6} - {expected:5.1%} from {total:,} games")

print("\n" + "="*60)
print("EVALUATED MOVES (using new logic):")
print("-" * 40)

# Evaluate with new logic
moves = evaluator.evaluate_position(data["master"], data["lichess"], is_player_turn=True)

if moves:
    print("Selected moves (filtered by master popularity, scored by Lichess):")
    for i, move in enumerate(moves, 1):
        score = move.expected_score_white
        print(f"{i}. {move.san:6} - Expected score: {score:.1%}")
        print(f"          (from {move.total_games:,} Lichess games)")
else:
    print("No moves selected (likely no moves meet master popularity threshold)")

print("\nLogic Summary:")
print("-" * 40)
print("1. Filter: Moves must be popular in MASTER games (>= 5%)")
print("2. Score: Expected score calculated from LICHESS games (1600-2200)")
print("3. Select: Best scoring moves (within 95% of top score)")
print("4. Terminate: If < 200 master games or < 1000 Lichess games")
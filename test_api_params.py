#!/usr/bin/env python3

import sys
sys.path.insert(0, 'src')

from lichess_client import LichessClient

# Create client
client = LichessClient()

# Test position (after 1.e4)
fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

# Show how rating ranges are calculated
min_rating = 1600
max_rating = 2200

rating_ranges = []
current = min_rating
while current < max_rating:
    rating_ranges.append(current)
    current += 200
if rating_ranges[-1] != max_rating:
    rating_ranges.append(max_rating)

print("Rating range calculation for 1600-2200:")
print(f"Rating points: {rating_ranges}")
print(f"Query parameter: ratings={','.join(map(str, rating_ranges))}")

print("\nActual API URLs being called:")
print("-" * 60)

# Master games URL
master_url = f"https://explorer.lichess.ovh/masters?fen={fen}&moves=12"
print(f"Master games:\n  {master_url}")

# Lichess games URL
lichess_params = {
    "fen": fen,
    "moves": 12,
    "ratings": ",".join(map(str, rating_ranges)),
    "speeds": "rapid,blitz"
}

# Build URL
from urllib.parse import urlencode
lichess_url = f"https://explorer.lichess.ovh/lichess?{urlencode(lichess_params)}"
print(f"\nLichess games:\n  {lichess_url}")

print("\n" + "="*60)
print("Explanation:")
print("-" * 40)
print("The ratings parameter works as follows:")
print("- Each number represents a rating bracket")
print("- 1600 = games from 1600-1800")
print("- 1800 = games from 1800-2000") 
print("- 2000 = games from 2000-2200")
print("- 2200 = games from 2200-2400")
print("\nSo 'ratings=1600,1800,2000,2200' gets games from 1600-2400")
print("(slightly wider than the configured 1600-2200 range)")
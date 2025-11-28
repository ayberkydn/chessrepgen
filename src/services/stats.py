from __future__ import annotations

from typing import Any


def calculate_moves_weighted_advantage(
    moves: list[dict],
    is_white: bool,
    aggregation_method: str = "median",
) -> float | None:
    """Combine move outcomes into a single advantage value.

    The aggregation method (weighted median or mean) is controllable through
    configuration so users can choose a more conservative or more smoothing
    approach when interpreting explorer data.
    """
    weighted_moves: list[tuple[float, float]] = []
    total_weight = 0.0

    for move_data in moves:
        move_total = (
            move_data.get("white", 0)
            + move_data.get("draws", 0)
            + move_data.get("black", 0)
        )

        if move_total == 0:
            continue

        white_rate = move_data.get("white", 0) / move_total
        black_rate = move_data.get("black", 0) / move_total

        if is_white:
            advantage = white_rate - black_rate
        else:
            advantage = black_rate - white_rate

        weighted_moves.append((advantage, move_total))
        total_weight += move_total

    if total_weight == 0 or not weighted_moves:
        return None

    agg_method = str(aggregation_method).lower()

    if agg_method == "mean":
        weighted_sum = sum(advantage * weight for advantage, weight in weighted_moves)
        return weighted_sum / total_weight

    # Default: weighted median for robustness against outliers
    # Sort ascending by advantage to find the true 50th percentile
    weighted_moves.sort(key=lambda item: item[0])
    half_weight = total_weight / 2
    cumulative = 0.0

    prev_advantage = weighted_moves[0][0]
    for advantage, weight in weighted_moves:
        cumulative += weight
        if cumulative >= half_weight:
            # If we're exactly at the midpoint, return this value
            # Otherwise interpolate between prev and current for more accuracy
            if cumulative - weight < half_weight:
                return advantage
            else:
                # Edge case: previous cumulative already passed half
                return advantage
        prev_advantage = advantage

    # Fallback: return the last (highest) advantage value
    return weighted_moves[-1][0]


def merge_reference_stats(
    master_stats: dict | None, highrating_stats: dict | None
) -> dict | None:
    sources = [stats for stats in (master_stats, highrating_stats) if stats]
    if not sources:
        return None

    merged: dict[str, Any] = {"white": 0, "draws": 0, "black": 0}
    move_map: dict[str, dict] = {}

    for stats in sources:
        merged["white"] += stats.get("white", 0)
        merged["draws"] += stats.get("draws", 0)
        merged["black"] += stats.get("black", 0)

        for move_data in stats.get("moves", []):
            uci = move_data.get("uci")
            if not uci:
                continue

            entry = move_map.get(uci)
            if not entry:
                entry = {
                    "uci": uci,
                    "san": move_data.get("san", ""),
                    "white": 0,
                    "draws": 0,
                    "black": 0,
                }
                if move_data.get("opening"):
                    entry["opening"] = move_data["opening"]
                move_map[uci] = entry

            entry["white"] += move_data.get("white", 0)
            entry["draws"] += move_data.get("draws", 0)
            entry["black"] += move_data.get("black", 0)

            games = (
                move_data.get("white", 0)
                + move_data.get("draws", 0)
                + move_data.get("black", 0)
            )

            avg_rating = move_data.get("averageRating")
            if games > 0 and avg_rating:
                entry.setdefault("_avg_sum", 0.0)
                entry.setdefault("_avg_games", 0)
                entry["_avg_sum"] += avg_rating * games
                entry["_avg_games"] += games

            if not entry.get("san"):
                entry["san"] = move_data.get("san", "")
            if not entry.get("opening") and move_data.get("opening"):
                entry["opening"] = move_data["opening"]

    merged_moves = []
    for entry in move_map.values():
        avg_games = entry.pop("_avg_games", 0)
        avg_sum = entry.pop("_avg_sum", 0.0)
        if avg_games > 0:
            entry["averageRating"] = avg_sum / avg_games
        merged_moves.append(entry)

    merged_moves.sort(
        key=lambda m: m.get("white", 0) + m.get("draws", 0) + m.get("black", 0),
        reverse=True,
    )
    merged["moves"] = merged_moves
    return merged


def total_games(stats: dict | None) -> int:
    if not stats:
        return 0
    return stats.get("white", 0) + stats.get("draws", 0) + stats.get("black", 0)

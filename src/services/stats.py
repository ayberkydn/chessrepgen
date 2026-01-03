from __future__ import annotations


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


def total_games(stats: dict | None) -> int:
    if not stats:
        return 0
    return stats.get("white", 0) + stats.get("draws", 0) + stats.get("black", 0)

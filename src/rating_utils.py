from __future__ import annotations

ALLOWED_LICHESS_RATINGS = [
    400,
    1000,
    1200,
    1400,
    1600,
    1800,
    2000,
    2200,
    2500,
]

PLAYER_POPULARITY_RATINGS = [2000, 2200, 2500]
PLAYER_POPULARITY_SPEEDS = ["rapid", "classical"]


def ensure_allowed_ratings(ratings: list[int]) -> list[int]:
    """Validate that ratings use allowed Lichess explorer brackets."""
    if not ratings:
        raise ValueError("ratings list must not be empty")

    invalid = [value for value in ratings if value not in ALLOWED_LICHESS_RATINGS]
    if invalid:
        allowed = ", ".join(map(str, ALLOWED_LICHESS_RATINGS))
        raise ValueError(
            f"Invalid rating bracket(s): {invalid}. Allowed values: {allowed}"
        )

    if ratings != sorted(ratings):
        raise ValueError("ratings must be sorted in ascending order")

    if len(set(ratings)) != len(ratings):
        raise ValueError("ratings must be unique")

    return ratings

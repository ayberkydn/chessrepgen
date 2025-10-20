from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MoveStats:
    uci: str
    san: str
    white_wins: int
    draws: int
    black_wins: int
    total_games: int

    @property
    def popularity(self) -> float:
        return self.total_games

    @property
    def expected_score_white(self) -> float:
        if self.total_games == 0:
            return 0.5
        return (self.white_wins + 0.5 * self.draws) / self.total_games

    @property
    def expected_score_black(self) -> float:
        if self.total_games == 0:
            return 0.5
        return (self.black_wins + 0.5 * self.draws) / self.total_games

    def expected_score(self, for_white: bool) -> float:
        return self.expected_score_white if for_white else self.expected_score_black


class MoveEvaluator:
    def __init__(self, config, side: str = "white"):
        self.config = config
        self.is_white = side == "white"

    def _opponent_popularity_threshold(self, depth: int) -> float:
        """Return the popularity threshold for opponent moves."""
        # Apply the relaxed threshold for the very first opponent move,
        # accounting for initial moves already played.
        if depth <= 1:
            return getattr(self.config, "first_move_min_opponent_popularity", 0.05)

        return self.config.min_opponent_popularity

    def parse_move_data(self, move_data: dict) -> MoveStats:
        return MoveStats(
            uci=move_data.get("uci", ""),
            san=move_data.get("san", ""),
            white_wins=move_data.get("white", 0),
            draws=move_data.get("draws", 0),
            black_wins=move_data.get("black", 0),
            total_games=move_data.get("white", 0)
            + move_data.get("draws", 0)
            + move_data.get("black", 0),
        )

    def evaluate_position(
        self,
        lichess_stats: dict | None,
        player_reference_stats: dict | None,
        is_player_turn: bool,
        depth: int = 0,
    ) -> list[MoveStats]:
        moves = []

        if is_player_turn and lichess_stats and lichess_stats.get("moves"):
            # For player moves: filter by reference popularity
            if not player_reference_stats or not player_reference_stats.get("moves"):
                logger.debug("No reference data available for player move filtering")
                return []

            total_reference_games = (
                player_reference_stats.get("white", 0)
                + player_reference_stats.get("draws", 0)
                + player_reference_stats.get("black", 0)
            )

            if total_reference_games < self.config.min_highrating_games:
                logger.debug(
                    "Insufficient reference games (%s < %s) - terminating",
                    total_reference_games,
                    self.config.min_highrating_games,
                )
                return []

            allowed_moves = set()
            for move_data in player_reference_stats["moves"]:
                uci = move_data.get("uci", "")
                if not uci:
                    continue
                move_total = (
                    move_data.get("white", 0)
                    + move_data.get("draws", 0)
                    + move_data.get("black", 0)
                )
                if total_reference_games == 0:
                    continue
                popularity = move_total / total_reference_games
                if popularity >= self.config.min_highrating_popularity:
                    allowed_moves.add(uci)

            if not allowed_moves:
                logger.debug(
                    "No moves meet reference popularity threshold %.1f%%",
                    self.config.min_highrating_popularity * 100,
                )
                return []

            # Keep only moves whose popularity clears the reference filter
            for move_data in lichess_stats["moves"]:
                uci = move_data.get("uci", "")
                if uci in allowed_moves:
                    move_stats = self.parse_move_data(move_data)
                    moves.append(move_stats)

            # Sort by Lichess score
            moves.sort(key=lambda m: m.expected_score(self.is_white), reverse=True)

            # For player's repertoire: return all moves within winrate tolerance of the best move
            if moves:
                best_score = moves[0].expected_score(self.is_white)

                # Use configured tolerance for the first move, then fall back to the standard tolerance
                if depth == 0:  # First player move only
                    tolerance = getattr(
                        self.config, "first_move_winrate_tolerance", 0.03
                    )
                else:  # All subsequent moves
                    tolerance = getattr(self.config, "winrate_tolerance", 0.05)

                # Select all moves within the tolerance range
                qualifying_moves = []
                for move in moves:
                    move_score = move.expected_score(self.is_white)
                    if best_score - move_score <= tolerance:
                        qualifying_moves.append(move)
                    else:
                        # Since moves are sorted by score, we can break early
                        break

                logger.debug(
                    f"Depth {depth}: Selected {len(qualifying_moves)} moves within {tolerance:.1%} tolerance of best score {best_score:.1%}"
                )
                return qualifying_moves

        elif not is_player_turn:
            # For opponent moves: use only Lichess data for popularity calculation
            # This better reflects what opponents actually play at the specified rating range

            if not lichess_stats or not lichess_stats.get("moves"):
                return []

            # Calculate total games from Lichess data only (for popularity calculation)
            lichess_total_for_popularity = 0
            lichess_moves = {}

            for move_data in lichess_stats["moves"]:
                uci = move_data.get("uci", "")
                if uci:
                    move_stats = self.parse_move_data(move_data)
                    lichess_moves[uci] = move_stats
                    lichess_total_for_popularity += move_stats.total_games

            # Filter moves by Lichess popularity
            if lichess_total_for_popularity > 0:
                popularity_threshold = self._opponent_popularity_threshold(depth)
                for uci, move_stats in lichess_moves.items():
                    popularity = move_stats.total_games / lichess_total_for_popularity
                    if popularity >= popularity_threshold:
                        moves.append(move_stats)

            moves.sort(key=lambda m: m.total_games, reverse=True)
            return moves[:10]

        return moves

    def should_terminate(
        self,
        depth: int,
        lichess_stats: dict | None,
    ) -> tuple[bool, str]:
        if depth > self.config.depth:
            return True, f"Maximum depth {self.config.depth} player moves reached"

        # Check if position is already very favorable based on Lichess winrate
        if lichess_stats:
            total_lichess = (
                lichess_stats.get("white", 0)
                + lichess_stats.get("draws", 0)
                + lichess_stats.get("black", 0)
            )

            if total_lichess > 0:
                # Calculate winrate from player's perspective
                if self.is_white:
                    winrate = (
                        lichess_stats.get("white", 0)
                        + 0.5 * lichess_stats.get("draws", 0)
                    ) / total_lichess
                else:
                    winrate = (
                        lichess_stats.get("black", 0)
                        + 0.5 * lichess_stats.get("draws", 0)
                    ) / total_lichess

                # Terminate if winrate is already very high (> 70%)
                if winrate > 0.70:
                    return (
                        True,
                        f"Position already very favorable (winrate: {winrate:.1%})",
                    )

            # Check for insufficient games
            min_lichess = getattr(self.config, "min_lichess_games", 1000)
            if total_lichess < min_lichess:
                return (
                    True,
                    f"Insufficient Lichess games ({total_lichess} < {min_lichess})",
                )
        else:
            return True, "No Lichess games data available"

        # No Stockfish evaluation - rely on winrate data only

        return False, ""

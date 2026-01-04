from __future__ import annotations

import logging

from models.evaluator import TerminationDecision
from models.stats import MoveStats

logger = logging.getLogger(__name__)


class MoveEvaluator:
    def __init__(self, config, side: str = "white"):
        self.config = config
        self.is_white = side == "white"

    def _opponent_popularity_threshold(self) -> float:
        """Return the popularity threshold for opponent moves."""
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

        # Log position evaluation start
        turn_type = "Player" if is_player_turn else "Opponent"
        logger.debug(
            "Evaluating position for %s turn at depth %d - Lichess data: %s",
            turn_type,
            depth,
            "available" if lichess_stats else "unavailable",
        )

        if is_player_turn and lichess_stats and lichess_stats.get("moves"):
            # For player moves: filter by advantage tolerance only
            candidate_moves: list[MoveStats] = []
            for move_data in lichess_stats["moves"]:
                move_stats = self.parse_move_data(move_data)
                candidate_moves.append(move_stats)

            if not candidate_moves:
                return []

            # Find best advantage among all moves
            baseline_advantage = max(
                (m.advantage(self.is_white) for m in candidate_moves), default=None
            )

            if baseline_advantage is None:
                return []

            # Keep moves within advantage tolerance of best move
            tolerance = getattr(self.config, "advantage_tolerance", 0.0)
            for move_stats in candidate_moves:
                advantage_value = move_stats.advantage(self.is_white)
                if baseline_advantage - advantage_value <= tolerance:
                    moves.append(move_stats)

            # Log player move filtering results
            logger.debug(
                "Player move filtering: %d total moves, %d passed advantage tolerance %.1f%%",
                len(candidate_moves),
                len(moves),
                tolerance * 100,
            )

            moves.sort(
                key=lambda m: (m.advantage(self.is_white), m.total_games),
                reverse=True,
            )
            return moves

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
            popularity_threshold = self._opponent_popularity_threshold()
            if lichess_total_for_popularity > 0:
                for uci, move_stats in lichess_moves.items():
                    popularity = move_stats.total_games / lichess_total_for_popularity
                    if popularity >= popularity_threshold:
                        moves.append(move_stats)

            # Log opponent move filtering results
            initial_moves_count = len(lichess_moves)
            if not moves and lichess_moves:
                fallback_count = getattr(self.config, "opponent_fallback_count", 1)
                if fallback_count > 0:
                    sorted_moves = sorted(
                        lichess_moves.values(),
                        key=lambda m: m.total_games,
                        reverse=True,
                    )
                    fallback = sorted_moves[:fallback_count]
                    moves.extend(fallback)
                    logger.debug(
                        "Depth %s: No opponent moves met popularity threshold %.1f%%; falling back to top %s move(s)",
                        depth,
                        popularity_threshold * 100,
                        fallback_count,
                    )

                logger.debug(
                    "Opponent move filtering: %d total moves, %d met threshold %.1f%%, %d after fallback",
                    initial_moves_count,
                    len(
                        [
                            m
                            for m in lichess_moves.values()
                            if (m.total_games / lichess_total_for_popularity)
                            >= popularity_threshold
                        ]
                    )
                    if lichess_total_for_popularity > 0
                    else 0,
                    popularity_threshold * 100,
                    len(moves),
                )
            else:
                logger.debug(
                    "Opponent move filtering: %d total moves, %d met threshold %.1f%%",
                    initial_moves_count,
                    len(moves),
                    popularity_threshold * 100,
                )

            moves.sort(key=lambda m: m.total_games, reverse=True)
            return moves[:10]

        return moves

    def should_terminate(
        self,
        depth: int,
        lichess_stats: dict | None,
    ) -> TerminationDecision:
        # Check if position is already very favorable based on Lichess winrate
        if lichess_stats:
            total_lichess = (
                lichess_stats.get("white", 0)
                + lichess_stats.get("draws", 0)
                + lichess_stats.get("black", 0)
            )

            # Check for insufficient games
            min_lichess = getattr(self.config, "min_lichess_games", 1000)
            if total_lichess < min_lichess:
                return TerminationDecision(
                    True,
                    f"Insufficient Lichess games ({total_lichess} < {min_lichess})",
                    True,
                )
        else:
            return TerminationDecision(True, "No Lichess games data available", True)

        # No Stockfish evaluation - rely on winrate data only
        return TerminationDecision(False, "", False)

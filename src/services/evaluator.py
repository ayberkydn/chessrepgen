from __future__ import annotations

import logging

from models.evaluator import TerminationDecision
from models.stats import MoveStats
from .stats import total_games

logger = logging.getLogger(__name__)


class MoveEvaluator:
    def __init__(self, config, side: str = "white"):
        self.config = config
        self.is_white = side == "white"

    def _opponent_popularity_threshold(self) -> float:
        """Return the popularity threshold for opponent moves."""
        return self.config.min_opponent_popularity

    def _player_popularity_threshold(self) -> float:
        """Return the popularity threshold for player moves."""
        return getattr(self.config, "min_player_popularity", 0.0)

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
            # For player moves: filter by advantage tolerance and popularity
            candidate_moves: list[MoveStats] = []
            total_games_at_pos = 0
            for move_data in lichess_stats["moves"]:
                move_stats = self.parse_move_data(move_data)
                candidate_moves.append(move_stats)
                total_games_at_pos += move_stats.total_games

            if not candidate_moves:
                return []

            padding_ratio = getattr(self.config, "padding_ratio", 0.02)
            parent_games = total_games(lichess_stats)
            padding = int(parent_games * padding_ratio)

            tolerance = getattr(self.config, "advantage_tolerance", 0.0)
            pop_threshold = self._player_popularity_threshold()

            # First, filter to moves that meet popularity threshold
            popular_moves = [
                m
                for m in candidate_moves
                if (m.total_games / total_games_at_pos if total_games_at_pos > 0 else 0)
                >= pop_threshold
            ]

            # Calculate baseline advantage from popular moves only
            # This prevents unpopular outliers from skewing the baseline
            if popular_moves:
                baseline_advantage = max(
                    (
                        m.advantage(
                            self.is_white,
                            padding_strength=padding,
                        )
                        for m in popular_moves
                    ),
                    default=None,
                )
            else:
                # Fallback: if no moves meet popularity threshold, use best move overall
                baseline_advantage = max(
                    (
                        m.advantage(
                            self.is_white,
                            padding_strength=padding,
                        )
                        for m in candidate_moves
                    ),
                    default=None,
                )

            if baseline_advantage is None:
                return []

            # Keep moves within advantage tolerance of best popular move AND meeting popularity threshold
            for move_stats in candidate_moves:
                advantage_value = move_stats.advantage(
                    self.is_white,
                    padding_strength=padding,
                )
                popularity = (
                    move_stats.total_games / total_games_at_pos
                    if total_games_at_pos > 0
                    else 0
                )

                if (baseline_advantage - advantage_value <= tolerance) and (
                    popularity >= pop_threshold
                ):
                    moves.append(move_stats)

            # Log player move filtering results
            logger.debug(
                "Player move filtering: %d total moves, %d popular, %d passed advantage tolerance %.1f%% and popularity %.1f%%",
                len(candidate_moves),
                len(popular_moves),
                len(moves),
                tolerance * 100,
                pop_threshold * 100,
            )

            moves.sort(
                key=lambda m: (
                    m.advantage(
                        self.is_white,
                        padding_strength=padding,
                    ),
                    m.total_games,
                ),
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

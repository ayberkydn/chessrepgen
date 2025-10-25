from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import NamedTuple

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
    def white_win_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return self.white_wins / self.total_games

    @property
    def black_win_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return self.black_wins / self.total_games

    @property
    def draw_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return self.draws / self.total_games

    def win_rate(self, for_white: bool) -> float:
        return self.white_win_rate if for_white else self.black_win_rate

    def win_margin(self, for_white: bool) -> float:
        """Difference between the player's and opponent's win percentages."""
        player_win_rate = self.win_rate(for_white)
        opponent_win_rate = self.win_rate(not for_white)
        return player_win_rate - opponent_win_rate


class TerminationDecision(NamedTuple):
    should_stop: bool
    reason: str
    applies_to_position: bool


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
            candidate_moves: list[MoveStats] = []
            best_margin: float | None = None
            for move_data in lichess_stats["moves"]:
                uci = move_data.get("uci", "")
                if uci in allowed_moves:
                    move_stats = self.parse_move_data(move_data)
                    candidate_moves.append(move_stats)
                    margin = move_stats.win_margin(self.is_white)
                    if best_margin is None or margin > best_margin:
                        best_margin = margin

            if not candidate_moves or best_margin is None:
                return []

            tolerance = getattr(self.config, "winrate_margin_tolerance", 0.0)
            if depth <= 1:
                tolerance = getattr(
                    self.config,
                    "first_move_winrate_margin_tolerance",
                    tolerance,
                )
            for move_stats in candidate_moves:
                margin = move_stats.win_margin(self.is_white)
                if best_margin - margin <= tolerance:
                    moves.append(move_stats)

            moves.sort(
                key=lambda m: (m.win_margin(self.is_white), m.total_games),
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
            popularity_threshold = self._opponent_popularity_threshold(depth)
            if lichess_total_for_popularity > 0:
                for uci, move_stats in lichess_moves.items():
                    popularity = move_stats.total_games / lichess_total_for_popularity
                    if popularity >= popularity_threshold:
                        moves.append(move_stats)

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

            moves.sort(key=lambda m: m.total_games, reverse=True)
            return moves[:10]

        return moves

    def should_terminate(
        self,
        depth: int,
        lichess_stats: dict | None,
    ) -> TerminationDecision:
        if depth > self.config.depth:
            return TerminationDecision(
                True,
                f"Maximum depth {self.config.depth} player moves reached",
                False,
            )

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

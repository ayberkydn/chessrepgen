import logging
from typing import Tuple
from dataclasses import dataclass
import chess

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
    def __init__(self, config, cache=None, side: str = "white"):
        self.config = config
        self.is_white = side == "white"

    def parse_move_data(self, move_data: dict, total_games: int) -> MoveStats:
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
        master_data: dict | None,
        lichess_data: dict | None,
        is_player_turn: bool,
        board: chess.Board | None = None,
        depth: int = 0,
    ) -> list[MoveStats]:
        moves = []

        if is_player_turn and lichess_data and lichess_data.get("moves"):
            # For player moves: filter by master popularity, but use Lichess data for expected score
            total_lichess_games = (
                lichess_data.get("white", 0)
                + lichess_data.get("draws", 0)
                + lichess_data.get("black", 0)
            )

            # Build a set of moves that meet master popularity threshold
            master_popular_moves = set()
            total_master_games = 0
            if master_data and master_data.get("moves"):
                total_master_games = (
                    master_data.get("white", 0)
                    + master_data.get("draws", 0)
                    + master_data.get("black", 0)
                )
                for move_data in master_data["moves"]:
                    if total_master_games > 0:
                        move_popularity = (
                            move_data.get("white", 0)
                            + move_data.get("draws", 0)
                            + move_data.get("black", 0)
                        ) / total_master_games
                        if move_popularity >= self.config.min_master_popularity:
                            master_popular_moves.add(move_data.get("uci", ""))

            # Check if we have sufficient master games
            if (
                len(master_popular_moves) == 0
                or total_master_games < self.config.min_master_games
            ):
                logger.debug(
                    f"Insufficient master games ({total_master_games} < {self.config.min_master_games}) - terminating"
                )
                return []

            # Build a dict of master move data for weighted score calculation
            master_moves_dict = {}
            if master_data and master_data.get("moves"):
                for move_data in master_data["moves"]:
                    uci = move_data.get("uci", "")
                    if uci:
                        master_moves_dict[uci] = move_data

            # Now evaluate moves from Lichess data that are either popular in master games or approved by Stockfish
            for move_data in lichess_data["moves"]:
                uci = move_data.get("uci", "")
                if uci in master_popular_moves:
                    move_stats = self.parse_move_data(move_data, total_lichess_games)
                    moves.append(move_stats)

            # Sort by Lichess score
            moves.sort(key=lambda m: m.expected_score(self.is_white), reverse=True)

            # For player's repertoire: return all moves within winrate tolerance of the best move
            if moves:
                best_score = moves[0].expected_score(self.is_white)

                # Use 0.025 tolerance for first move only, then use configured tolerance
                if depth == 0:  # First player move only
                    tolerance = 0.03
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

            if lichess_data and lichess_data.get("moves"):
                total_lichess = (
                    lichess_data.get("white", 0)
                    + lichess_data.get("draws", 0)
                    + lichess_data.get("black", 0)
                )

                # Calculate total games from Lichess data only (for popularity calculation)
                lichess_total_for_popularity = 0
                lichess_moves = {}

                for move_data in lichess_data["moves"]:
                    uci = move_data.get("uci", "")
                    if uci:
                        move_stats = self.parse_move_data(move_data, total_lichess)
                        lichess_moves[uci] = move_stats
                        lichess_total_for_popularity += move_stats.total_games

                # Filter moves by Lichess popularity
                if lichess_total_for_popularity > 0:
                    for uci, move_stats in lichess_moves.items():
                        popularity = (
                            move_stats.total_games / lichess_total_for_popularity
                        )
                        if popularity >= self.config.min_popularity:
                            moves.append(move_stats)

                moves.sort(key=lambda m: m.total_games, reverse=True)
                return moves[:10]

            # Fallback to master data if no Lichess data available
            elif master_data and master_data.get("moves"):
                total_master = (
                    master_data.get("white", 0)
                    + master_data.get("draws", 0)
                    + master_data.get("black", 0)
                )

                master_total_for_popularity = 0
                master_moves = {}

                for move_data in master_data["moves"]:
                    uci = move_data.get("uci", "")
                    if uci:
                        move_stats = self.parse_move_data(move_data, total_master)
                        master_moves[uci] = move_stats
                        master_total_for_popularity += move_stats.total_games

                if master_total_for_popularity > 0:
                    for uci, move_stats in master_moves.items():
                        popularity = (
                            move_stats.total_games / master_total_for_popularity
                        )
                        if popularity >= self.config.min_popularity:
                            moves.append(move_stats)

                moves.sort(key=lambda m: m.total_games, reverse=True)
                return moves[:10]

        return moves

    def should_terminate(
        self,
        depth: int,
        master_data: dict | None,
        lichess_data: dict | None,
        board: chess.Board | None = None,
    ) -> tuple[bool, str]:
        if depth > self.config.depth:
            return True, f"Maximum depth {self.config.depth} player moves reached"

        # Check if position is already very favorable based on Lichess winrate
        if lichess_data:
            total_lichess = (
                lichess_data.get("white", 0)
                + lichess_data.get("draws", 0)
                + lichess_data.get("black", 0)
            )

            if total_lichess > 0:
                # Calculate winrate from player's perspective
                if self.is_white:
                    winrate = (
                        lichess_data.get("white", 0)
                        + 0.5 * lichess_data.get("draws", 0)
                    ) / total_lichess
                else:
                    winrate = (
                        lichess_data.get("black", 0)
                        + 0.5 * lichess_data.get("draws", 0)
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

from __future__ import annotations

import logging
import chess
from dataclasses import dataclass
from collections import deque
from lichess_client import LichessClient
from cache import ChessCache
from evaluator import MoveEvaluator, MoveStats
from rating_utils import (
    PLAYER_POPULARITY_RATINGS,
    PLAYER_POPULARITY_SPEEDS,
)

logger = logging.getLogger(__name__)


@dataclass
class RepertoireNode:
    board: chess.Board
    move: chess.Move | None
    move_san: str | None
    stats: MoveStats | None
    depth: int
    is_player_turn: bool
    termination_reason: str | None
    children: list["RepertoireNode"]
    comment: str = ""
    position_stats: dict | None = None  # Store position statistics for terminal nodes

    def add_child(self, child: "RepertoireNode"):
        self.children.append(child)


@dataclass
class RepertoireLine:
    """Represents a fully constructed repertoire line rooted at a position."""

    initial_moves: str
    root: RepertoireNode


class RepertoireBuilder:
    def __init__(self, config, side: str):
        self.config = config
        self.side = side
        proxies = None
        if getattr(config, "use_proxy", True):
            proxies = [
                "http://opsmwgon:c9splz41ut21@142.111.48.253:7030",
                "http://opsmwgon:c9splz41ut21@31.59.20.176:6754",
                "http://opsmwgon:c9splz41ut21@38.170.176.177:5572",
                "http://opsmwgon:c9splz41ut21@198.23.239.134:6540",
                "http://opsmwgon:c9splz41ut21@45.38.107.97:6014",
                "http://opsmwgon:c9splz41ut21@107.172.163.27:6543",
                "http://opsmwgon:c9splz41ut21@64.137.96.74:6641",
                "http://opsmwgon:c9splz41ut21@216.10.27.159:6837",
                "http://opsmwgon:c9splz41ut21@142.111.67.146:5611",
                "http://opsmwgon:c9splz41ut21@142.147.128.93:6593",
            ]
        else:
            logger.info("Proxy usage disabled via configuration.")
        self.client = LichessClient(proxies=proxies)
        self.cache = ChessCache(config.cache_file)
        self.evaluator = MoveEvaluator(config, side)
        self.is_white = side == "white"
        self.visited_positions: set[str] = set()

    def _total_games(self, stats: dict | None) -> int:
        if not stats:
            return 0
        return stats.get("white", 0) + stats.get("draws", 0) + stats.get("black", 0)

    def _merge_reference_stats(
        self, master_stats: dict | None, highrating_stats: dict | None
    ) -> dict | None:
        sources = [stats for stats in (master_stats, highrating_stats) if stats]
        if not sources:
            return None

        merged = {"white": 0, "draws": 0, "black": 0}
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

    def parse_initial_moves(self, moves_str: str) -> list[chess.Move]:
        board = chess.Board()
        moves = []

        move_parts = moves_str.strip().split()
        for move_str in move_parts:
            try:
                move = board.parse_san(move_str)
                moves.append(move)
                board.push(move)
            except:
                try:
                    move = chess.Move.from_uci(move_str)
                    if move in board.legal_moves:
                        moves.append(move)
                        board.push(move)
                    else:
                        logger.error(f"Illegal move: {move_str}")
                        raise ValueError(f"Illegal move: {move_str}")
                except:
                    logger.error(f"Invalid move format: {move_str}")
                    raise ValueError(f"Invalid move format: {move_str}")

        return moves

    def get_position_data(self, fen: str) -> dict:
        cached_lichess_stats = self.cache.get_lichess_stats(
            fen,
            self.config.ratings,
            self.config.time_control,
        )
        cached_master_stats = self.cache.get_master_stats(fen)
        cached_highrating_stats = self.cache.get_lichess_stats(
            fen,
            PLAYER_POPULARITY_RATINGS,
            PLAYER_POPULARITY_SPEEDS,
        )

        lichess_stats = cached_lichess_stats
        master_stats = cached_master_stats
        highrating_stats = cached_highrating_stats
        player_reference_stats = None
        player_reference_source: str | None = None
        combined_stats: dict | None = None

        if not cached_lichess_stats:
            try:
                api_data = self.client.get_position_stats(
                    fen,
                    self.config.ratings,
                    self.config.time_control,
                )
            except Exception:
                logger.exception("Failed to fetch Lichess explorer data")
                api_data = None
            if api_data and api_data.get("lichess"):
                lichess_stats = api_data["lichess"]
                self.cache.set_lichess_stats(
                    fen,
                    lichess_stats,
                    self.config.ratings,
                    self.config.time_control,
                )

        if not master_stats:
            try:
                master_stats = self.client.get_master_games(fen)
            except Exception:
                logger.exception("Failed to fetch master game data")
                master_stats = None
            if master_stats:
                self.cache.set_master_stats(fen, master_stats)

        master_total = self._total_games(master_stats)
        if master_stats:
            player_reference_stats = master_stats
            player_reference_source = "master"

        if master_total < self.config.min_highrating_games:
            if master_total > 0:
                logger.debug(
                    "Master games below threshold for %s (%s < %s); attempting fallback",
                    fen,
                    master_total,
                    self.config.min_highrating_games,
                )
            if not highrating_stats:
                try:
                    highrating_stats = self.client.get_lichess_games(
                        fen,
                        PLAYER_POPULARITY_RATINGS,
                        PLAYER_POPULARITY_SPEEDS,
                    )
                except Exception:
                    logger.exception("Failed to fetch high-rating fallback data")
                    highrating_stats = None
                if highrating_stats:
                    self.cache.set_lichess_stats(
                        fen,
                        highrating_stats,
                        PLAYER_POPULARITY_RATINGS,
                        PLAYER_POPULARITY_SPEEDS,
                    )
            # Blend master and fallback high-rating snapshots so thresholds see the full sample
            combined_stats = self._merge_reference_stats(master_stats, highrating_stats)
            if combined_stats:
                player_reference_stats = combined_stats
                if master_stats and highrating_stats:
                    player_reference_source = "combined"
                elif highrating_stats:
                    player_reference_source = "highrating"
                else:
                    player_reference_source = "master"

        if not player_reference_stats:
            if master_stats:
                player_reference_stats = master_stats
                player_reference_source = "master"
            elif highrating_stats:
                player_reference_stats = highrating_stats
                player_reference_source = "highrating"

        return {
            "lichess": lichess_stats,
            "player_reference": player_reference_stats,
            "player_reference_source": player_reference_source,
            "master_reference": master_stats,
            "highrating_reference": highrating_stats,
            "combined_reference": combined_stats,
        }

    def _set_no_candidate_moves_termination(
        self,
        node: RepertoireNode,
        is_player_turn: bool,
    ) -> None:
        """Annotate node when no candidate moves are available."""
        position_stats = node.position_stats or {}
        lichess_stats = position_stats.get("lichess")
        player_reference_stats = position_stats.get("player_reference")
        player_reference_source = position_stats.get("player_reference_source")
        master_stats = position_stats.get("master_reference")
        highrating_stats = position_stats.get("highrating_reference")
        combined_stats = position_stats.get("combined_reference")

        if is_player_turn:
            total_reference_games = self._total_games(player_reference_stats)
            master_total = self._total_games(master_stats)
            highrating_total = self._total_games(highrating_stats)
            combined_total = self._total_games(combined_stats)

            if total_reference_games < self.config.min_highrating_games:
                if player_reference_source == "highrating":
                    reason = (
                        f"High-rating games below threshold ({total_reference_games} < "
                        f"{self.config.min_highrating_games})"
                    )
                elif player_reference_source == "master":
                    fallback_note = (
                        f"; fallback total {highrating_total}"
                        if highrating_total > 0
                        else "; no high-rating fallback data"
                    )
                    reason = (
                        f"Master games below threshold ({total_reference_games} < "
                        f"{self.config.min_highrating_games}){fallback_note}"
                    )
                elif player_reference_source == "combined":
                    reason = (
                        "Combined master/high-rating games below threshold "
                        f"({total_reference_games} < {self.config.min_highrating_games}; "
                        f"master={master_total}, high-rating={highrating_total})"
                    )
                else:
                    reason = (
                        f"Reference games below threshold ({total_reference_games} < "
                        f"{self.config.min_highrating_games})"
                    )
            elif player_reference_stats and player_reference_stats.get("moves"):
                if player_reference_source == "highrating":
                    reason = "No high-rating moves meet popularity threshold"
                elif player_reference_source == "master":
                    reason = "No master moves meet popularity threshold"
                elif player_reference_source == "combined":
                    reason = (
                        "No combined master/high-rating moves meet popularity threshold"
                    )
                else:
                    reason = "No reference moves meet popularity threshold"
            else:
                if player_reference_source == "highrating":
                    reason = "No high-rating fallback data available"
                elif player_reference_source == "master":
                    if master_total > 0:
                        reason = "No master moves available"
                    else:
                        reason = "No master game data available"
                elif player_reference_source == "combined":
                    if combined_total > 0:
                        reason = "No combined master/high-rating moves available"
                    else:
                        reason = "No combined master/high-rating data available"
                else:
                    reason = "No reference game data available"
        else:
            has_lichess_moves = bool(lichess_stats and lichess_stats.get("moves"))
            if not has_lichess_moves:
                reason = "No opponent move data available"
            else:
                reason = "No opponent moves meet popularity threshold"

        node.termination_reason = reason
        if node.comment:
            if reason not in node.comment:
                node.comment = f"{node.comment} | {reason}"
        else:
            node.comment = reason

    def build_repertoire(self) -> list[RepertoireLine]:
        lines: list[RepertoireLine] = []

        initial_move_sequences = (
            self.config.initial_moves_white
            if self.side == "white"
            else self.config.initial_moves_black
        )

        for initial_moves_str in initial_move_sequences:
            logger.info(f"Building repertoire for: {initial_moves_str}")

            try:
                board = chess.Board()
                initial_moves = self.parse_initial_moves(initial_moves_str)

                for move in initial_moves:
                    board.push(move)

                root = self.build_node_breadth_first(board)
                if root:
                    lines.append(RepertoireLine(initial_moves_str, root))

            except Exception as e:
                logger.error(f"Error building repertoire for {initial_moves_str}: {e}")
                continue

        return lines

    def build_node_breadth_first(self, board: chess.Board) -> RepertoireNode | None:
        """Build repertoire tree using breadth-first search approach."""
        fen = board.fen()
        if fen in self.visited_positions:
            logger.debug(f"Position already visited: {fen[:20]}...")
            return None

        self.visited_positions.add(fen)
        is_player_turn = (board.turn == chess.WHITE) == self.is_white

        # Create root node
        root = RepertoireNode(
            board=board.copy(),
            move=None,
            move_san=None,
            stats=None,
            depth=0,
            is_player_turn=is_player_turn,
            termination_reason=None,
            children=[],
        )

        # Check for immediate termination conditions
        if board.is_game_over():
            result = board.result()
            root.termination_reason = f"Game over: {result}"
            root.comment = f"Game ends: {result}"
            return root

        position_data = self.get_position_data(fen)
        lichess_stats = position_data["lichess"]
        root.position_stats = position_data

        should_stop, reason = self.evaluator.should_terminate(0, lichess_stats)

        if should_stop:
            root.termination_reason = reason
            root.comment = reason
            return root

        queue = deque([root])

        while queue:
            node = queue.popleft()

            if node.termination_reason:
                continue

            current_board = node.board.copy()
            current_is_player_turn = node.is_player_turn

            # Get candidate moves for this position
            candidate_moves = self.evaluator.evaluate_position(
                node.position_stats["lichess"],
                node.position_stats.get("player_reference"),
                current_is_player_turn,
                node.depth,
            )

            if not candidate_moves:
                self._set_no_candidate_moves_termination(
                    node,
                    current_is_player_turn,
                )
                continue

            # Process each candidate move
            child_added = False
            for move_stats in candidate_moves:
                try:
                    child_board = current_board.copy()
                    move = chess.Move.from_uci(move_stats.uci)

                    if move not in child_board.legal_moves:
                        logger.warning(f"Illegal move from API: {move_stats.uci}")
                        continue

                    san = child_board.san(move)
                    child_board.push(move)

                    child_fen = child_board.fen()
                    if child_fen in self.visited_positions:
                        logger.debug(
                            f"Child position already visited: {child_fen[:20]}..."
                        )
                        continue

                    self.visited_positions.add(child_fen)

                    # Calculate child depth (only increment on player's turn)
                    child_depth = node.depth
                    if current_is_player_turn:
                        child_depth += 1

                    # Create child node
                    child_is_player_turn = (
                        child_board.turn == chess.WHITE
                    ) == self.is_white
                    child_node = RepertoireNode(
                        board=child_board.copy(),
                        move=move,
                        move_san=san,
                        stats=move_stats,
                        depth=child_depth,
                        is_player_turn=child_is_player_turn,
                        termination_reason=None,
                        children=[],
                    )

                    # Check termination conditions for child
                    child_terminated = False

                    if child_board.is_game_over():
                        result = child_board.result()
                        child_node.termination_reason = f"Game over: {result}"
                        child_node.comment = f"Game ends: {result}"
                        child_terminated = True
                    else:
                        child_position_data = self.get_position_data(child_fen)
                        child_node.position_stats = child_position_data

                        should_stop_child, reason_child = (
                            self.evaluator.should_terminate(
                                child_depth,
                                child_position_data["lichess"],
                            )
                        )

                        if should_stop_child:
                            child_node.termination_reason = reason_child
                            child_node.comment = reason_child
                            child_terminated = True

                    # Add statistics comment
                    score = move_stats.expected_score(self.is_white)
                    stats_comment = f"Score: {score:.1%}"
                    if child_node.termination_reason:
                        child_node.comment = (
                            f"{stats_comment} | {child_node.termination_reason}"
                        )
                    else:
                        child_node.comment = stats_comment

                    # Add child to parent
                    node.add_child(child_node)
                    child_added = True

                    # If child is not terminated and we haven't exceeded max depth, continue exploring
                    if not child_terminated and child_depth <= self.config.depth:
                        queue.append(child_node)

                except Exception as e:
                    logger.error(f"Error processing move {move_stats.uci}: {e}")
                    continue

            if not child_added and not node.termination_reason:
                node.termination_reason = "Transposes to previously analyzed line"
                if node.comment:
                    if node.termination_reason not in node.comment:
                        node.comment = f"{node.comment} | {node.termination_reason}"
                else:
                    node.comment = node.termination_reason

        return root

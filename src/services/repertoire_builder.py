from __future__ import annotations

import logging
from collections import deque
from heapq import heappop, heappush
from itertools import count

import chess

from models.graph import RepertoireEdge, RepertoireLine, RepertoireNode

from .cache import ChessCache
from .evaluator import MoveEvaluator
from .lichess_client import LichessClient
from .pruner import RepertoirePruner
from .stats import total_games

logger = logging.getLogger(__name__)


class RepertoireBuilder:
    def __init__(self, config, side: str):
        self.config = config
        self.side = side
        self.is_white = side == "white"

        self.client = LichessClient()
        self.cache = ChessCache(config.cache_file)
        self.evaluator = MoveEvaluator(config, side)
        self.pruner = RepertoirePruner(config, self.is_white)

        self.nodes_by_key: dict[str, RepertoireNode] = {}
        self._expanded_keys: set[str] = set()
        self._heap_counter = count()
        self._move_sequence_cache: dict[str, str] = {}  # Memoization for move sequences

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

                root = self._build_graph_from_board(board)
                if root:
                    lines.append(RepertoireLine(initial_moves_str, root))

            except Exception as e:
                logger.error(f"Error building repertoire for {initial_moves_str}: {e}")
                continue

        return lines

    def compute_terminal_advantages(self, roots: list[RepertoireNode]) -> None:
        self.pruner.compute_terminal_advantages(roots)

    def evaluate_and_combine_terminal_scores(self, roots: list[RepertoireNode]) -> None:
        """Evaluate terminal nodes with Stockfish and combine with terminal_advantage."""
        self.pruner.evaluate_and_combine_terminal_scores(roots)

    def _reconstruct_move_sequence(self, node: RepertoireNode) -> str:
        """Reconstruct the move sequence from start position to the given node.

        Results are memoized by node.key to avoid redundant computation.
        """
        # Check memoization cache first
        cached = self._move_sequence_cache.get(node.key)
        if cached is not None:
            return cached

        try:
            # Use the board's move stack to get the actual sequence of moves
            board_copy = node.board.copy()

            # If the board has no moves played, it's the starting position
            if not board_copy.move_stack:
                result = "starting position"
                self._move_sequence_cache[node.key] = result
                return result

            # Get the move history and convert to SAN notation
            temp_board = chess.Board()
            moves_san = []

            for move in board_copy.move_stack:
                san = temp_board.san(move)
                moves_san.append(san)
                temp_board.push(move)

            # Format the move sequence
            if len(moves_san) <= 6:
                result = f"{' '.join(moves_san)}"
            else:
                # Show first 3 moves, last 3 moves with ellipsis
                result = f"{' '.join(moves_san[:3])} ... {' '.join(moves_san[-3:])}"

            self._move_sequence_cache[node.key] = result
            return result

        except Exception:
            # Fallback to a simple representation if reconstruction fails
            try:
                ply_count = node.board.fullmove_number * 2 - (
                    1 if node.board.turn == chess.WHITE else 0
                )
                result = f"ply {ply_count} ({node.board.fen()[:8]}...)"
            except Exception:
                result = f"position {node.key[:8]}..."
            self._move_sequence_cache[node.key] = result
            return result

    def parse_initial_moves(self, moves_str: str) -> list[chess.Move]:
        board = chess.Board()
        moves = []

        move_parts = moves_str.strip().split()
        for raw_move_str in move_parts:
            # Handle move numbers (e.g. "1.", "1.e4", "1...c5")
            if raw_move_str[0].isdigit():
                if raw_move_str.endswith("."):
                    continue
                move_str = (
                    raw_move_str.split(".")[-1] if "." in raw_move_str else raw_move_str
                )
            else:
                move_str = raw_move_str

            if not move_str:
                continue

            try:
                move = board.parse_san(move_str)
                moves.append(move)
                board.push(move)
            except (
                chess.InvalidMoveError,
                chess.IllegalMoveError,
                chess.AmbiguousMoveError,
                ValueError,
            ):
                # SAN parsing failed, try UCI format
                try:
                    move = chess.Move.from_uci(move_str)
                    if move in board.legal_moves:
                        moves.append(move)
                        board.push(move)
                    else:
                        logger.error(f"Illegal move: {move_str}")
                        raise ValueError(f"Illegal move: {move_str}")
                except ValueError as e:
                    logger.error(f"Invalid move format: {move_str}")
                    raise ValueError(f"Invalid move format: {move_str}") from e

        return moves

    def get_position_data(
        self,
        fen: str,
        *,
        depth: int | None = None,
        line: str | None = None,
    ) -> tuple[dict | None, bool]:
        # Log position data fetching
        logger.debug("Fetching position data for FEN: %s", fen[:20] + "...")

        line_display = (line or "(start)").strip()
        if len(line_display) > 80:
            line_display = line_display[:77] + "..."
        depth_display = depth if depth is not None else "N/A"
        request_context = f"depth={depth_display}, line={line_display}"

        cached_lichess_stats = self.cache.get_lichess_stats(
            fen,
            self.config.ratings,
            self.config.time_control,
        )
        lichess_stats = cached_lichess_stats
        lichess_stats_fetched_from_api = False

        # Log cache status
        if cached_lichess_stats:
            logger.debug("Cache hit for Lichess data")
        else:
            logger.debug("Cache miss - fetching from API")

        if not cached_lichess_stats:
            lichess_stats_fetched_from_api = True
            try:
                logger.debug("Fetching Lichess explorer data for position...")
                api_data = self.client.get_position_stats(
                    fen,
                    self.config.ratings,
                    self.config.time_control,
                    request_context=f"Primary | {request_context}",
                )
            except Exception:
                logger.exception("Failed to fetch Lichess explorer data")
                api_data = None
            if api_data and api_data.get("lichess"):
                lichess_stats = api_data["lichess"]
                logger.debug("Successfully fetched and cached Lichess data")
                self.cache.set_lichess_stats(
                    fen,
                    lichess_stats,
                    self.config.ratings,
                    self.config.time_control,
                )

        if lichess_stats_fetched_from_api:
            lichess_total = total_games(lichess_stats)
            logger.info(
                "Position data ready - Lichess games: %d",
                lichess_total,
            )

        return (
            {
                "lichess": lichess_stats,
            },
            lichess_stats_fetched_from_api,
        )

    def _reset_graph_state(self) -> None:
        self.nodes_by_key.clear()
        self._expanded_keys.clear()
        self._heap_counter = count()
        self._move_sequence_cache.clear()

    def _ensure_position_data(
        self,
        node: RepertoireNode,
        *,
        depth: int | None = None,
        line: str | None = None,
    ) -> tuple[dict, bool]:
        """Fetch and cache position data for a node.

        Returns an empty dict if data cannot be fetched, ensuring callers
        always receive a dict (never None).

        Returns a tuple of (data_dict, lichess_fetched_from_api).
        """
        # Early return if already fetched - avoid any unnecessary work
        if node.position_stats is not None:
            return node.position_stats, False

        if depth is None:
            depth = node.min_player_depth
        if line is None:
            line = self._reconstruct_move_sequence(node)
        fetched_data, lichess_fetched_from_api = self.get_position_data(
            node.fen,
            depth=depth,
            line=line,
        )
        # Ensure we always store a dict, never None
        node.position_stats = fetched_data if fetched_data is not None else {}
        return node.position_stats, lichess_fetched_from_api

    def _propagate_ancestors(self, node: RepertoireNode, ancestors: set[str]) -> None:
        missing = ancestors - node.ancestors
        if not missing:
            return

        queue: deque[RepertoireNode] = deque([node])
        while queue:
            current = queue.popleft()
            diff = ancestors - current.ancestors
            if not diff:
                continue
            current.ancestors |= diff
            for edge in current.edges:
                queue.append(edge.child)

    def _get_or_create_node_from_board(
        self,
        board: chess.Board,
        ancestors: set[str],
    ) -> RepertoireNode:
        key = self._position_key(board)
        existing = self.nodes_by_key.get(key)
        if existing:
            if ancestors:
                self._propagate_ancestors(existing, ancestors)
            return existing

        node = RepertoireNode(
            board=board.copy(),
            fen=board.fen(),
            key=key,
            is_player_turn=(board.turn == chess.WHITE) == self.is_white,
            ancestors=set(ancestors),
        )
        self.nodes_by_key[key] = node
        return node

    def _position_key(self, board: chess.Board) -> str:
        return board.epd()

    def _expand_node(
        self,
        node: RepertoireNode,
        heap: list[tuple[int, int, RepertoireNode]],
    ) -> None:
        # Log the position being analyzed with move sequence from start
        position_description = self._reconstruct_move_sequence(node)
        depth_for_evaluator = node.min_player_depth or 0

        position_stats, lichess_fetched_from_api = self._ensure_position_data(
            node,
            depth=depth_for_evaluator,
            line=position_description,
        )
        lichess_stats = position_stats.get("lichess")
        player_turn = "White" if node.board.turn == chess.WHITE else "Black"
        side_indicator = "(player)" if node.is_player_turn else "(opponent)"

        if lichess_fetched_from_api:
            lichess_total = total_games(lichess_stats)
            logger.info(
                "Analyzing position: %s - Turn: %s %s - Depth: %s - Lichess games: %d",
                position_description,
                player_turn,
                side_indicator,
                depth_for_evaluator,
                lichess_total,
            )

        candidate_moves = self.evaluator.evaluate_position(
            lichess_stats,
            None,
            node.is_player_turn,
            depth_for_evaluator,
        )

        # Log candidate moves being considered
        if candidate_moves:
            min_games = getattr(self.config, "min_lichess_games", 1000)
            padding = getattr(self.config, "padding_strength", 0)

            moves_info = []
            for move in candidate_moves[:5]:  # Show top 5 moves
                side_label = "White" if self.is_white else "Black"
                advantage = (
                    move.advantage(
                        self.is_white,
                        min_games_threshold=min_games,
                        padding_strength=padding,
                    )
                    * 100
                )
                moves_info.append(
                    f"{move.san} ({advantage:+.1f}%, {move.total_games} games)"
                )

            logger.debug(
                "Found %d candidate moves at %s: %s%s",
                len(candidate_moves),
                self._reconstruct_move_sequence(node),
                ", ".join(moves_info),
                "..." if len(candidate_moves) > 5 else "",
            )

        if not candidate_moves:
            logger.debug(
                "TERMINAL_MARGINS: No candidate moves found during node expansion. "
                "Position: %s, FEN: %s, Player turn: %s, Move depth: %s, "
                "Position stats available: %s, Ancestors count: %d",
                node.key,
                node.board.fen(),
                node.is_player_turn,
                getattr(node, "min_player_depth", "UNKNOWN"),
                node.position_stats is not None,
                len(node.ancestors),
            )
            self._set_no_candidate_moves_termination(node, node.is_player_turn)
            return

        ancestors_with_current = set(node.ancestors)
        ancestors_with_current.add(node.key)

        added_edge = False
        cycle_detected = False

        for move_stats in candidate_moves:
            try:
                move = chess.Move.from_uci(move_stats.uci)
            except ValueError:
                logger.warning("Invalid move from API: %s", move_stats.uci)
                continue

            board_copy = node.board.copy()
            if move not in board_copy.legal_moves:
                logger.warning("Illegal move from API: %s", move_stats.uci)
                continue

            san = board_copy.san(move)
            board_copy.push(move)
            child_key = self._position_key(board_copy)

            if child_key in ancestors_with_current:
                cycle_detected = True
                continue

            child_ancestors = ancestors_with_current.copy()

            child_node = self._get_or_create_node_from_board(
                board_copy, child_ancestors
            )

            resulting_depth = depth_for_evaluator + (1 if node.is_player_turn else 0)

            game_over_reason = None
            if board_copy.is_game_over():
                game_result = board_copy.result()
                game_over_reason = f"Game over: {game_result}"

            edge_reason = ""
            edge_terminal = False

            if game_over_reason:
                edge_terminal = True
                edge_reason = game_over_reason
                if not child_node.termination_reason:
                    child_node.termination_reason = game_over_reason
                    child_node.comment = game_over_reason
                child_description = self._reconstruct_move_sequence(child_node)
                self._ensure_position_data(
                    child_node,
                    depth=resulting_depth,
                    line=child_description,
                )
            else:
                child_description = self._reconstruct_move_sequence(child_node)
                child_stats, _ = self._ensure_position_data(
                    child_node,
                    depth=resulting_depth,
                    line=child_description,
                )
                termination_decision = self.evaluator.should_terminate(
                    resulting_depth,
                    child_stats.get("lichess"),
                )

                edge_terminal = termination_decision.should_stop

                if termination_decision.should_stop and termination_decision.reason:
                    edge_reason = termination_decision.reason
                    if termination_decision.applies_to_position:
                        if not child_node.termination_reason:
                            child_node.termination_reason = termination_decision.reason
                            child_node.comment = termination_decision.reason
                elif child_node.termination_reason:
                    edge_terminal = True
                    edge_reason = child_node.termination_reason

            side_label = "White" if self.is_white else "Black"

            min_games = getattr(self.config, "min_lichess_games", 1000)
            padding = getattr(self.config, "padding_strength", 0)

            advantage = (
                move_stats.advantage(
                    self.is_white,
                    min_games_threshold=min_games,
                    padding_strength=padding,
                )
                * 100
            )
            comment_parts = [
                f"{side_label} advantage: {advantage:.1f}",
                f"Samples: {move_stats.total_games}",
            ]
            if edge_reason:
                comment_parts.append(edge_reason)
            edge_comment = " | ".join(comment_parts)

            edge = RepertoireEdge(
                parent=node,
                child=child_node,
                move=move,
                move_san=san,
                stats=move_stats,
                resulting_depth=resulting_depth,
                comment=edge_comment,
                termination_reason=edge_reason or None,
                is_terminal=edge_terminal or bool(child_node.termination_reason),
            )

            node.add_edge(edge)
            added_edge = True

            if edge.is_terminal:
                continue

            new_depth = resulting_depth
            current_depth = child_node.min_player_depth
            if current_depth is None or new_depth < current_depth:
                child_node.min_player_depth = new_depth
                heappush(heap, (new_depth, next(self._heap_counter), child_node))

        if not added_edge and not node.termination_reason:
            if cycle_detected:
                node.termination_reason = "All continuations repeat earlier positions"
            else:
                node.termination_reason = "No valid continuations available"
            node.comment = (
                f"{node.comment} | {node.termination_reason}"
                if node.comment
                else node.termination_reason
            )

    def _build_graph_from_board(
        self,
        board: chess.Board,
    ) -> RepertoireNode:
        self._reset_graph_state()

        root = self._get_or_create_node_from_board(
            board,
            set(),
        )
        root.min_player_depth = 0
        root_description = self._reconstruct_move_sequence(root)
        root_stats, _ = self._ensure_position_data(
            root,
            depth=0,
            line=root_description,
        )

        termination_decision = self.evaluator.should_terminate(
            0,
            root_stats.get("lichess"),
        )

        if termination_decision.should_stop:
            if termination_decision.applies_to_position:
                root.termination_reason = termination_decision.reason
            if termination_decision.reason:
                root.comment = termination_decision.reason
            return root

        heap: list[tuple[int, int, RepertoireNode]] = []
        heappush(heap, (0, next(self._heap_counter), root))

        while heap:
            depth, _, node = heappop(heap)
            if node.termination_reason:
                continue
            if node.min_player_depth is None or depth != node.min_player_depth:
                continue
            if node.key in self._expanded_keys:
                continue

            self._expanded_keys.add(node.key)
            self._expand_node(node, heap)

        return root

    def _set_no_candidate_moves_termination(
        self,
        node: RepertoireNode,
        is_player_turn: bool,
    ) -> None:
        """Annotate node when no candidate moves are available."""
        position_stats = node.position_stats or {}
        lichess_stats = position_stats.get("lichess")

        # Log detailed information about why no candidate moves were found
        logger.debug(
            "TERMINAL_MARGINS: No candidate moves found for position. "
            "Position: %s, FEN: %s, Player turn: %s, "
            "Lichess moves available: %s",
            node.key,
            node.board.fen(),
            is_player_turn,
            bool(lichess_stats and lichess_stats.get("moves")),
        )

        if is_player_turn:
            has_lichess_moves = bool(lichess_stats and lichess_stats.get("moves"))
            if not has_lichess_moves:
                reason = "No player move data available"
            else:
                reason = (
                    "No player moves meet advantage tolerance and popularity threshold"
                )
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

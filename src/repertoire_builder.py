from __future__ import annotations

import logging
import chess
from dataclasses import dataclass, field
from collections import deque
from heapq import heappush, heappop
from itertools import count
from lichess_client import LichessClient
from cache import ChessCache
from evaluator import MoveEvaluator, MoveStats


logger = logging.getLogger(__name__)
PLAYER_POPULARITY_RATINGS = [2000, 2200, 2500]
PLAYER_POPULARITY_SPEEDS = ["rapid", "classical"]


@dataclass
class RepertoireNode:
    board: chess.Board
    fen: str
    key: str
    is_player_turn: bool
    comment: str = ""
    termination_reason: str | None = None
    position_stats: dict | None = None
    edges: list["RepertoireEdge"] = field(default_factory=list)
    ancestors: set[str] = field(default_factory=set)
    min_player_depth: int | None = None
    terminal_win_margin: float | None = None

    def add_edge(self, edge: "RepertoireEdge") -> None:
        self.edges.append(edge)


@dataclass
class RepertoireEdge:
    parent: RepertoireNode
    child: RepertoireNode
    move: chess.Move
    move_san: str
    stats: MoveStats | None
    resulting_depth: int
    comment: str = ""
    termination_reason: str | None = None
    is_terminal: bool = False
    is_best_continuation: bool = False


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
        self.nodes_by_key: dict[str, RepertoireNode] = {}
        self._expanded_keys: set[str] = set()
        self._heap_counter = count()

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

    def _reset_graph_state(self) -> None:
        self.nodes_by_key.clear()
        self._expanded_keys.clear()
        self._heap_counter = count()

    def _ensure_position_data(self, node: RepertoireNode) -> dict:
        if node.position_stats is None:
            node.position_stats = self.get_position_data(node.fen)
        return node.position_stats

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
        position_stats = self._ensure_position_data(node)
        lichess_stats = position_stats.get("lichess")
        player_reference = position_stats.get("player_reference")
        depth_for_evaluator = node.min_player_depth or 0

        candidate_moves = self.evaluator.evaluate_position(
            lichess_stats,
            player_reference,
            node.is_player_turn,
            depth_for_evaluator,
        )

        if not candidate_moves:
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
                child_stats = self._ensure_position_data(child_node)
            else:
                child_stats = self._ensure_position_data(child_node)
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
            win_margin = move_stats.win_margin(self.is_white) * 100
            comment_parts = [
                f"{side_label} win margin: {win_margin:.1f}",
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

    def _build_graph_from_board(self, board: chess.Board) -> RepertoireNode:
        self._reset_graph_state()

        root = self._get_or_create_node_from_board(board, set())
        root.min_player_depth = 0
        root_stats = self._ensure_position_data(root)

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

    def _compute_terminal_win_margin(
        self,
        node: RepertoireNode,
        cache: dict[str, float | None],
    ) -> float | None:
        cached = cache.get(node.key)
        if cached is not None or node.key in cache:
            node.terminal_win_margin = cached
            return cached

        if not node.edges:
            node.terminal_win_margin = None
            cache[node.key] = None
            return None

        child_values: list[tuple[float, float]] = []
        total_weight = 0.0

        for edge in node.edges:
            margin: float | None = None
            child_node = edge.child
            if edge.is_terminal:
                if edge.stats:
                    margin = edge.stats.win_margin(self.is_white)
                    if child_node:
                        child_node.terminal_win_margin = margin
                        cache[child_node.key] = margin
            else:
                if child_node:
                    margin = self._compute_terminal_win_margin(child_node, cache)
                if margin is None and edge.stats:
                    margin = edge.stats.win_margin(self.is_white)

            if margin is None and edge.stats:
                margin = edge.stats.win_margin(self.is_white)
                if child_node and child_node.terminal_win_margin is None:
                    child_node.terminal_win_margin = margin
                    cache[child_node.key] = margin

            if margin is None:
                continue

            weight = float(edge.stats.total_games) if edge.stats else 0.0
            child_values.append((margin, weight))
            total_weight += weight

        if not child_values:
            node.terminal_win_margin = None
            cache[node.key] = None
            return None

        if node.is_player_turn:
            terminal_value = max(margin for margin, _ in child_values)
        else:
            if total_weight > 0:
                terminal_value = (
                    sum(margin * weight for margin, weight in child_values)
                    / total_weight
                )
            else:
                terminal_value = sum(margin for margin, _ in child_values) / len(
                    child_values
                )

        node.terminal_win_margin = terminal_value
        cache[node.key] = terminal_value
        return terminal_value

    def compute_terminal_win_margins(self, roots: list[RepertoireNode]) -> None:
        cache: dict[str, float | None] = {}
        for root in roots:
            self._compute_terminal_win_margin(root, cache)

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

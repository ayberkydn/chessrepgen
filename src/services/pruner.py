from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.graph import RepertoireEdge, RepertoireNode

from .stats import calculate_moves_weighted_advantage, total_games

logger = logging.getLogger(__name__)


class RepertoirePruner:
    def __init__(self, config, is_white: bool):
        self.config = config
        self.is_white = is_white

    def compute_terminal_advantages(self, roots: list[RepertoireNode]) -> None:
        cache: dict[str, float | None] = {}
        for root in roots:
            self._compute_terminal_advantage(root, cache)
        if getattr(self.config, "prune_non_best_moves", False):
            self._prune_to_best_edges(roots)

    def _compute_terminal_advantage(
        self,
        node: RepertoireNode,
        cache: dict[str, float | None],
    ) -> float | None:
        cached = cache.get(node.key)
        if cached is not None or node.key in cache:
            node.terminal_advantage = cached
            return cached

        if not node.edges:
            logger.debug(
                "TERMINAL_ADVANTAGES: Node has no edges - setting terminal_advantage to None. "
                "Position: %s, FEN: %s, Player turn: %s, Move depth: %s",
                node.key,
                node.board.fen(),
                node.is_player_turn,
                getattr(node, "min_player_depth", "UNKNOWN"),
            )
            node.terminal_advantage = None
            cache[node.key] = None
            return None

        child_values: list[tuple[float, float]] = []
        total_weight = 0.0

        for edge in node.edges:
            advantage_value: float | None = None
            child_node = edge.child
            if edge.is_terminal:
                # For terminal edges, calculate the weighted median advantage of the resulting position
                if child_node:
                    advantage_value = self._calculate_position_advantage(child_node)
                    if advantage_value is not None:
                        child_node.terminal_advantage = advantage_value
                        cache[child_node.key] = advantage_value
                # Fallback to move's own advantage if position calculation fails
                if advantage_value is None and edge.stats:
                    advantage_value = edge.stats.advantage(self.is_white)
                    if child_node:
                        child_node.terminal_advantage = advantage_value
                        cache[child_node.key] = advantage_value
            else:
                if child_node:
                    advantage_value = self._compute_terminal_advantage(
                        child_node, cache
                    )
                if advantage_value is None and edge.stats:
                    advantage_value = edge.stats.advantage(self.is_white)

            if advantage_value is None and edge.stats:
                advantage_value = edge.stats.advantage(self.is_white)
                if child_node and child_node.terminal_advantage is None:
                    child_node.terminal_advantage = advantage_value
                    cache[child_node.key] = advantage_value

            if advantage_value is None:
                continue

            weight = float(edge.stats.total_games) if edge.stats else 0.0
            child_values.append((advantage_value, weight))
            total_weight += weight

        if not child_values:
            logger.debug(
                "TERMINAL_ADVANTAGES: All child nodes have None terminal advantages - setting parent to None. "
                "Position: %s, FEN: %s, Player turn: %s, Move depth: %s, "
                "Number of children: %d",
                node.key,
                node.board.fen(),
                node.is_player_turn,
                getattr(node, "min_player_depth", "UNKNOWN"),
                len(node.edges),
            )
            node.terminal_advantage = None
            cache[node.key] = None
            return None

        if node.is_player_turn:
            terminal_value = max(advantage for advantage, _ in child_values)
        else:
            if total_weight > 0:
                terminal_value = (
                    sum(advantage * weight for advantage, weight in child_values)
                    / total_weight
                )
            else:
                terminal_value = sum(advantage for advantage, _ in child_values) / len(
                    child_values
                )

        node.terminal_advantage = terminal_value
        cache[node.key] = terminal_value
        return terminal_value

    def _calculate_position_advantage(self, node: RepertoireNode) -> float | None:
        """
        Calculate the advantage of a position as the weighted median of all possible moves
        based solely on Lichess data.
        """
        position_stats = node.position_stats
        if not position_stats:
            return None

        lichess_stats = position_stats.get("lichess")

        if lichess_stats and lichess_stats.get("moves"):
            agg_method = getattr(self.config, "advantage_aggregation", "median")
            lichess_advantage = calculate_moves_weighted_advantage(
                lichess_stats["moves"], self.is_white, agg_method
            )
            if lichess_advantage is not None:
                return lichess_advantage

        # Fall back to position's overall stats if no moves available
        if lichess_stats:
            total = (
                lichess_stats.get("white", 0)
                + lichess_stats.get("draws", 0)
                + lichess_stats.get("black", 0)
            )

            if total > 0:
                white_rate = lichess_stats.get("white", 0) / total
                black_rate = lichess_stats.get("black", 0) / total

                if self.is_white:
                    return white_rate - black_rate
                else:
                    return black_rate - white_rate

        return None

    def _prune_to_best_edges(self, roots: list[RepertoireNode]) -> None:
        visited: set[str] = set()
        for root in roots:
            self._prune_node(root, visited)

    def _prune_node(
        self,
        node: RepertoireNode,
        visited: set[str],
    ) -> None:
        if node.key in visited:
            return

        visited.add(node.key)

        if node.is_player_turn and node.edges:
            best_edge: RepertoireEdge | None = None
            best_advantage: float | None = None

            for edge in node.edges:
                child_advantage = edge.child.terminal_advantage if edge.child else None
                if child_advantage is None:
                    logger.debug(
                        "TERMINAL_ADVANTAGES: Edge has None child advantage during pruning. "
                        "Position: %s, Move: %s (%s), Child exists: %s, "
                        "Child terminal advantage: %s, Edge stats available: %s",
                        node.key,
                        edge.move_san,
                        edge.move.uci() if edge.move else "N/A",
                        edge.child is not None,
                        child_advantage,
                        edge.stats is not None if edge.stats else False,
                    )
                    continue
                if best_advantage is None or child_advantage > best_advantage:
                    best_advantage = child_advantage
                    best_edge = edge

            if best_edge is not None:
                alternative_scores: list[tuple[str, float]] = []
                for edge in node.edges:
                    is_best = edge is best_edge
                    edge.is_best_continuation = is_best
                    if not is_best:
                        if not edge.is_terminal:
                            edge.is_terminal = True
                        # Store terminal advantage on edge before pruning
                        edge_terminal_advantage = (
                            edge.child.terminal_advantage if edge.child else None
                        )
                        if edge_terminal_advantage is None:
                            logger.debug(
                                "TERMINAL_ADVANTAGES: Pruned edge will have None terminal advantage. "
                                "Position: %s, Move: %s (%s), Child FEN: %s, "
                                "Edge was terminal: %s, Termination reason: %s",
                                node.key,
                                edge.move_san,
                                edge.move.uci() if edge.move else "N/A",
                                edge.child.board.fen() if edge.child else "N/A",
                                edge.is_terminal,
                                edge.termination_reason or "NONE",
                            )
                        edge.terminal_advantage = edge_terminal_advantage
                        if edge_terminal_advantage is not None:
                            alternative_scores.append(
                                (edge.move_san, edge_terminal_advantage)
                            )
                        edge.child = None

                if alternative_scores:
                    alternative_scores.sort(key=lambda item: item[1], reverse=True)
                    best_edge.pruned_alternative_scores = alternative_scores
                node.edges = [best_edge]

        for edge in node.edges:
            child = edge.child
            if child and not edge.is_terminal:
                self._prune_node(child, visited)

    def post_prune(self, roots: list[RepertoireNode]) -> None:
        """Apply post-generation pruning based on depth and game count thresholds."""
        max_depth = getattr(self.config, "postprune_max_depth", None)
        min_games = getattr(self.config, "postprune_min_games", 0) or 0

        if max_depth is None and min_games <= 0:
            return

        logger.info(
            "Applying post-pruning (max depth: %s, min games: %s)",
            max_depth if max_depth is not None else "disabled",
            min_games if min_games > 0 else "disabled",
        )

        visited: set[str] = set()
        for root in roots:
            self._post_prune_node(root, visited, max_depth, min_games)

    def _post_prune_node(
        self,
        node: RepertoireNode,
        visited: set[str],
        max_depth: int | None,
        min_games: int,
    ) -> None:
        if node.key in visited:
            return

        visited.add(node.key)

        for edge in list(node.edges):
            child = edge.child
            if child is None:
                continue

            prune_reason: str | None = None
            child_depth = (
                child.min_player_depth
                if child.min_player_depth is not None
                else edge.resulting_depth
            )

            if (
                max_depth is not None
                and child_depth is not None
                and child_depth > max_depth
            ):
                prune_reason = (
                    f"Post-pruned: depth {child_depth} exceeds limit {max_depth}"
                )

            if prune_reason is None and min_games > 0:
                game_count = self._get_position_game_count(child)
                if game_count < min_games:
                    prune_reason = (
                        f"Post-pruned: {game_count} games < minimum {min_games}"
                    )

            if prune_reason:
                logger.debug(
                    "POST_PRUNE: Pruning edge %s -> %s (%s)",
                    node.key,
                    child.key,
                    prune_reason,
                )
                self._make_edge_terminal(edge, prune_reason)
                continue

            if not edge.is_terminal:
                self._post_prune_node(child, visited, max_depth, min_games)

    def _make_edge_terminal(self, edge: RepertoireEdge, reason: str | None) -> None:
        """Mark an edge as terminal and detach the child while preserving advantages."""
        edge.is_terminal = True
        if reason:
            edge.termination_reason = reason
            if edge.comment:
                if reason not in edge.comment:
                    edge.comment = f"{edge.comment} | {reason}"
            else:
                edge.comment = reason

        terminal_advantage = None
        if edge.child and edge.child.terminal_advantage is not None:
            terminal_advantage = edge.child.terminal_advantage
        elif edge.stats:
            terminal_advantage = edge.stats.advantage(self.is_white)

        edge.terminal_advantage = terminal_advantage
        edge.child = None

    def _get_position_game_count(self, node: RepertoireNode) -> int:
        """Return the best available total game count for a position."""
        stats = node.position_stats
        if not stats:
            return 0

        preferred_sources = [
            "lichess",
            "player_reference",
            "combined_reference",
            "master_reference",
            "highrating_reference",
        ]

        for key in preferred_sources:
            source = stats.get(key)
            if source:
                return total_games(source)

        return 0

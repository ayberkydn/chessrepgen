"""Tree analyzer for calculating expected winrates of alternative moves.

This module analyzes the completed repertoire tree to determine which alternative
moves have the best expected outcomes based on probability-weighted terminal nodes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
import chess

from tree_utils import (
    iter_terminal_probabilities,
    remove_descendants,
)

logger = logging.getLogger(__name__)


class TreeAnalyzer:
    """Analyzes repertoire trees to evaluate alternative moves."""

    def __init__(self, config):
        self.config = config

    def analyze_alternative_moves(self, roots: list["RepertoireNode"]) -> None:
        """Analyze all alternative moves in the repertoire tree.

        Args:
            roots: List of root nodes in the repertoire tree
        """
        logger.info("Analyzing alternative moves...")

        analyzed_count = 0
        for root in roots:
            analyzed_count += self._analyze_node_recursive(root)

        logger.info(f"Analyzed {analyzed_count} positions with alternative moves")

    def _analyze_node_recursive(self, node: "RepertoireNode") -> int:
        """Recursively analyze nodes for alternative moves.

        Args:
            node: Current node to analyze

        Returns:
            Number of positions analyzed with alternatives
        """
        analyzed_count = 0

        # Recursively analyze children first so deeper alternatives are resolved
        if node.children:
            # Copy to avoid issues if pruning mutates child list
            for child in list(node.children):
                analyzed_count += self._analyze_node_recursive(child)

        # Now analyze this node's alternatives (player turn nodes only)
        if self._is_player_turn_with_alternatives(node):
            self._analyze_position_alternatives(node)
            self._prune_player_alternatives(node)
            analyzed_count += 1

        return analyzed_count

    def _is_player_turn_with_alternatives(self, node: "RepertoireNode") -> bool:
        """Check if node represents player turn with multiple alternative moves.

        Args:
            node: Node to check

        Returns:
            True if this is player turn with alternatives
        """
        if not node.children:
            return False

        # Check if this is player's turn and has multiple children
        return node.is_player_turn and len(node.children) > 1

    def _analyze_position_alternatives(self, node: "RepertoireNode") -> None:
        """Analyze alternative moves at a position.

        Args:
            node: Node with alternative moves
        """
        logger.debug(f"Analyzing alternatives at position {node.move_san or 'start'}")

        # Calculate expected winrate for each alternative
        for child in node.children:
            expected_winrate = self._calculate_move_expected_winrate(child)
            child.expected_winrate = expected_winrate

            logger.debug(
                f"Move {child.move_san}: Expected winrate = {expected_winrate:.1%}"
            )

        # Sort children by expected winrate (best first)
        node.children.sort(
            key=lambda x: getattr(x, "expected_winrate", 0), reverse=True
        )

        # Add analysis comments
        self._add_analysis_comments(node)

    def _prune_player_alternatives(self, node: "RepertoireNode") -> None:
        """Prune player alternatives so only the best continuation keeps its subtree."""
        if not node.children:
            setattr(node, "best_child", None)
            return

        best_child = node.children[0]
        setattr(node, "best_child", best_child)
        setattr(best_child, "is_best_continuation", True)

        # All other moves lose their continuation so we assume best play later
        for child in node.children[1:]:
            setattr(child, "is_best_continuation", False)
            if child.children:
                remove_descendants(child)
            self._tag_pruning_comment(child)

    def _tag_pruning_comment(self, node: "RepertoireNode") -> None:
        """Annotate nodes whose branches were removed during pruning."""
        expected = getattr(node, "expected_winrate", None)
        if expected is not None:
            reason = "[PRUNED]"
        else:
            reason = "[PRUNED]"

        node.termination_reason = reason

        if node.comment:
            if reason not in node.comment:
                node.comment += f" | {reason}"
        else:
            node.comment = reason

    def _calculate_move_expected_winrate(self, start_node: "RepertoireNode") -> float:
        """Calculate expected winrate for a move by analyzing terminal nodes.

        Args:
            start_node: Starting node for the move to analyze

        Returns:
            Expected winrate (0.0 to 1.0)
        """
        terminals = iter_terminal_probabilities(
            start_node,
            follow_best=True,
            assume_uniform_if_missing=True,
        )

        if not terminals:
            logger.warning(f"No terminal nodes found for move {start_node.move_san}")
            return 0.5  # Default to 50% if no terminals found

        total_weighted_winrate = 0.0
        total_probability = 0.0

        for terminal, path_probability in terminals:
            if terminal.position_stats and terminal.position_stats.get("lichess"):
                lichess_data = terminal.position_stats["lichess"]

                # Calculate winrate from player's perspective
                total_games = (
                    lichess_data.get("white", 0)
                    + lichess_data.get("draws", 0)
                    + lichess_data.get("black", 0)
                )

                if total_games > 0:
                    # Determine winrate based on which side we're building for
                    if self.config.side == "white":
                        white_wins = lichess_data.get("white", 0)
                        draws = lichess_data.get("draws", 0)
                        winrate = (white_wins + 0.5 * draws) / total_games
                    else:
                        black_wins = lichess_data.get("black", 0)
                        draws = lichess_data.get("draws", 0)
                        winrate = (black_wins + 0.5 * draws) / total_games

                    weighted_contribution = path_probability * winrate
                    total_weighted_winrate += weighted_contribution
                    total_probability += path_probability

                    logger.debug(
                        f"Terminal: {terminal.move_san or 'end'}, "
                        f"Path prob: {path_probability:.3f}, "
                        f"Winrate: {winrate:.1%}, "
                        f"Contribution: {weighted_contribution:.3f}"
                    )

        if total_probability == 0:
            logger.warning(f"No valid probability paths for move {start_node.move_san}")
            return 0.5

        expected_winrate = total_weighted_winrate / total_probability

        return expected_winrate

    def _add_analysis_comments(self, node: "RepertoireNode") -> None:
        """Add analysis comments to the node and its children.

        Args:
            node: Node to add comments to
        """
        for i, child in enumerate(node.children):
            expected_winrate = getattr(child, "expected_winrate", 0)

            # Add ranking information
            rank = i + 1
            total_alternatives = len(node.children)

            analysis_comment = f"Expected: {expected_winrate:.1%}"

            # Append to existing comments
            if child.comment:
                child.comment += f" | {analysis_comment}"
            else:
                child.comment = analysis_comment


def analyze_tree(roots: list["RepertoireNode"], config) -> None:
    """Convenience function to analyze a repertoire tree.

    Args:
        roots: List of root nodes
        config: Configuration object
    """
    analyzer = TreeAnalyzer(config)
    analyzer.analyze_alternative_moves(roots)

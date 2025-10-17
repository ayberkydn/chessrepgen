"""Tree pruner for removing continuations after suboptimal moves.

This module prunes the repertoire tree after alternative analysis by:
1. Identifying the best move (highest expected winrate) at each position
2. Keeping full continuations for the best move
3. Removing all continuations for suboptimal moves
4. Preserving suboptimal moves as terminal nodes with analysis
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tree_utils import count_descendants, count_nodes, remove_descendants

if TYPE_CHECKING:
    from repertoire_builder import RepertoireNode

logger = logging.getLogger(__name__)


class TreePruner:
    """Prunes repertoire trees to focus on best continuations."""

    def __init__(self, config):
        self.config = config
        self.pruned_count = 0
        self.preserved_count = 0

    def prune_tree(self, roots: list["RepertoireNode"]) -> None:
        """Prune all trees in the repertoire.

        Args:
            roots: List of root nodes in the repertoire tree
        """
        logger.info("Starting tree pruning...")
        self.pruned_count = 0
        self.preserved_count = 0

        for root in roots:
            self._prune_node_recursive(root)

        logger.info(
            f"Pruning complete: {self.pruned_count} continuations pruned, "
            f"{self.preserved_count} best-move continuations preserved"
        )

    def _prune_node_recursive(self, node: "RepertoireNode") -> None:
        """Recursively prune nodes in the tree.

        Args:
            node: Current node to prune
        """
        # Check if this is a player turn node with multiple alternatives and expected winrates
        if (
            node.children
            and len(node.children) > 1
            and hasattr(node, "is_player_turn")
            and node.is_player_turn
        ):
            # Find the best move (highest expected winrate)
            best_child = self._find_best_move(node.children)

            if best_child:
                # Prune all suboptimal moves
                for child in node.children:
                    if child == best_child:
                        # Keep full continuation for best move
                        self.preserved_count += 1
                        self._prune_node_recursive(child)
                    else:
                        # Prune continuation for suboptimal move
                        self._prune_suboptimal_move(child)
            else:
                # No expected winrates found, don't prune
                for child in node.children:
                    self._prune_node_recursive(child)
        else:
            # Single child, opponent turn, or no expected winrates, continue recursion
            for child in node.children:
                self._prune_node_recursive(child)

    def _find_best_move(
        self, children: list["RepertoireNode"]
    ) -> Optional["RepertoireNode"]:
        """Find the child with the highest expected winrate.

        Args:
            children: List of child nodes

        Returns:
            Child node with highest expected winrate, or None if no expected winrates found
        """
        best_child = None
        best_winrate = -1.0

        for child in children:
            expected_winrate = getattr(child, "expected_winrate", None)
            if expected_winrate is not None and expected_winrate > best_winrate:
                best_winrate = expected_winrate
                best_child = child

        return best_child

    def _prune_suboptimal_move(self, node: "RepertoireNode") -> None:
        """Prune a suboptimal move by removing all its children.

        Args:
            node: Suboptimal move node to prune
        """
        if node.children:
            # Count total nodes being pruned (including all descendants)
            nodes_removed = count_descendants(node)
            self.pruned_count += nodes_removed

            # Remove all children
            remove_descendants(node)

            # Add pruning comment
            expected_winrate = getattr(node, "expected_winrate", None)
            if expected_winrate is not None:
                pruning_comment = f"[PRUNED] Suboptimal move - expected winrate: {expected_winrate:.1%}"
            else:
                pruning_comment = (
                    "[PRUNED] Suboptimal move - no expected winrate calculated"
                )

            node.termination_reason = pruning_comment

            if node.comment:
                if pruning_comment not in node.comment:
                    node.comment += f" | {pruning_comment}"
            else:
                node.comment = pruning_comment

            logger.debug(
                f"Pruned {nodes_removed} nodes after {node.move_san} ({pruning_comment})"
            )

    def get_pruning_summary(self, roots: list["RepertoireNode"]) -> str:
        """Generate a summary of pruning results.

        Args:
            roots: List of root nodes

        Returns:
            Summary string with pruning statistics
        """
        total_nodes_before = sum(count_nodes(root) for root in roots)
        total_nodes_after = sum(count_nodes(root) for root in roots)
        nodes_removed = total_nodes_before - total_nodes_after

        summary = f"Tree Pruning Summary:\n"
        summary += f"  Total nodes before pruning: {total_nodes_before}\n"
        summary += f"  Total nodes after pruning: {total_nodes_after}\n"
        summary += f"  Nodes removed: {nodes_removed}\n"
        summary += f"  Best-move continuations preserved: {self.preserved_count}\n"
        summary += f"  Suboptimal continuations pruned: {self.pruned_count}"

        return summary


def prune_tree(roots: List["RepertoireNode"], config) -> None:
    """Convenience function to prune a repertoire tree.

    Args:
        roots: List of root nodes
        config: Configuration object
    """
    pruner = TreePruner(config)
    pruner.prune_tree(roots)
    return pruner

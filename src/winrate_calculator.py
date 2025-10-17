from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from dataclasses import dataclass
import chess

if TYPE_CHECKING:
    from repertoire_builder import RepertoireNode

from tree_utils import (
    calculate_path_probability,
    collect_terminal_paths,
    path_to_moves,
)

logger = logging.getLogger(__name__)


@dataclass
class TerminalNode:
    """Represents a terminal node with its path and evaluation"""

    node: "RepertoireNode"
    path: list["RepertoireNode"]
    probability: float
    expected_score: float


class WinrateCalculator:
    """Calculates expected winrate over all terminal nodes in a repertoire tree"""

    def __init__(self, config, side: str = "white"):
        self.config = config
        self.is_white = side == "white"

    def calculate_expected_winrate(self, roots: list) -> dict:
        """
        Calculate the expected winrate across all terminal nodes

        Returns:
            Dict with winrate statistics including overall winrate,
            number of terminal nodes, and weighted paths
        """
        terminal_paths: list[list["RepertoireNode"]] = []
        for root in roots:
            terminal_paths.extend(
                collect_terminal_paths(root, stop_on_termination=True)
            )

        if not terminal_paths:
            logger.warning("No terminal nodes found")
            return {"expected_winrate": 0.5, "terminal_count": 0, "weighted_paths": []}

        terminal_nodes = [
            TerminalNode(node=path[-1], path=path, probability=0, expected_score=0)
            for path in terminal_paths
        ]

        # Calculate probabilities and weighted scores
        total_probability = 0
        weighted_score = 0
        weighted_paths = []

        for terminal in terminal_nodes:
            # Calculate probability of reaching this terminal node
            probability = calculate_path_probability(terminal.path)

            # Get expected score at terminal position
            expected_score = self._get_terminal_expected_score(terminal.node)

            # Weight the score by probability
            weighted_score += probability * expected_score
            total_probability += probability

            path_data = {
                "moves": path_to_moves(terminal.path),
                "probability": probability,
                "expected_score": expected_score,
                "contribution": probability * expected_score,
                "termination_reason": terminal.node.termination_reason,
            }

            weighted_paths.append(path_data)

        # Sort weighted paths by contribution
        weighted_paths.sort(key=lambda x: x["contribution"], reverse=True)

        # Calculate final winrate
        if total_probability > 0:
            expected_winrate = weighted_score / total_probability
        else:
            expected_winrate = 0.5

        result = {
            "expected_winrate": expected_winrate,
            "terminal_count": len(terminal_nodes),
            "total_probability": total_probability,
            "weighted_paths": weighted_paths[:10],  # Top 10 most significant paths
        }

        return result

    def calculate_node_winrate(self, node) -> float:
        """Calculate the expected winrate at any node using only Lichess statistics"""
        if not (hasattr(node, "position_stats") and node.position_stats):
            return 0.5

        lichess_data = node.position_stats.get("lichess")

        if lichess_data:
            lichess_white = lichess_data.get("white", 0)
            lichess_draws = lichess_data.get("draws", 0)
            lichess_black = lichess_data.get("black", 0)
            lichess_total = lichess_white + lichess_draws + lichess_black

            if lichess_total > 0:
                if self.is_white:
                    return (lichess_white + 0.5 * lichess_draws) / lichess_total
                else:
                    return (lichess_black + 0.5 * lichess_draws) / lichess_total

        return 0.5

    def _get_terminal_expected_score(self, node) -> float:
        """Get the expected score at a terminal position using Lichess statistics"""
        return self.calculate_node_winrate(node)

    def _calculate_winrate_breakdown(self, roots: list) -> dict:
        """Calculate winrate breakdown using only Lichess statistics"""
        terminal_paths: list[list["RepertoireNode"]] = []
        for root in roots:
            terminal_paths.extend(
                collect_terminal_paths(root, stop_on_termination=True)
            )

        if not terminal_paths:
            return {"lichess": None}

        weighted_lichess = 0
        total_probability = 0

        for path in terminal_paths:
            probability = calculate_path_probability(path)

            terminal = path[-1]

            if hasattr(terminal, "position_stats") and terminal.position_stats:
                lichess_data = terminal.position_stats.get("lichess")

                # Calculate Lichess score
                if lichess_data:
                    lichess_white = lichess_data.get("white", 0)
                    lichess_draws = lichess_data.get("draws", 0)
                    lichess_black = lichess_data.get("black", 0)
                    lichess_total = lichess_white + lichess_draws + lichess_black

                    if lichess_total > 0:
                        if self.is_white:
                            lichess_score = (
                                lichess_white + 0.5 * lichess_draws
                            ) / lichess_total
                        else:
                            lichess_score = (
                                lichess_black + 0.5 * lichess_draws
                            ) / lichess_total
                        weighted_lichess += probability * lichess_score

            total_probability += probability

        if total_probability > 0:
            lichess_avg = weighted_lichess / total_probability
        else:
            lichess_avg = 0.5

        return {"lichess": lichess_avg}

    def get_detailed_statistics_per_initial(
        self, roots: list, initial_moves: list[str]
    ) -> str:
        """Generate detailed statistics for each initial move separately"""
        output = []
        output.append("\n=== Expected Winrate Analysis by Initial Moves ===")
        output.append("(Using Lichess statistics only)")

        for i, (root, initial_move_str) in enumerate(zip(roots, initial_moves)):
            stats = self.calculate_expected_winrate([root])
            breakdown = self._calculate_winrate_breakdown([root])

            output.append(f"\nInitial moves: {initial_move_str}")
            output.append(f"  Expected Winrate: {stats['expected_winrate']:.1%}")

            # Show breakdown
            if breakdown["lichess"] is not None:
                output.append(f"    Lichess winrate: {breakdown['lichess']:.1%}")

            output.append(f"  Terminal Positions: {stats['terminal_count']}")
            output.append(f"  Path Probability: {stats['total_probability']:.3f}")

        # Also calculate overall if multiple initial moves
        if len(roots) > 1:
            overall_stats = self.calculate_expected_winrate(roots)
            breakdown = self._calculate_winrate_breakdown(roots)

            output.append(f"\nOverall (all initial moves combined):")
            output.append(
                f"  Expected Winrate: {overall_stats['expected_winrate']:.1%}"
            )

            # Show breakdown
            if breakdown["lichess"] is not None:
                output.append(f"    Lichess winrate: {breakdown['lichess']:.1%}")

            output.append(f"  Terminal Positions: {overall_stats['terminal_count']}")
            output.append(
                f"  Path Probability: {overall_stats['total_probability']:.3f}"
            )

        return "\n".join(output)

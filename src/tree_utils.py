"""Shared helper utilities for repertoire tree operations."""

from __future__ import annotations

from typing import Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from repertoire_builder import RepertoireNode


def remove_descendants(node: "RepertoireNode") -> None:
    """Remove all descendants from a node."""
    for child in list(node.children):
        remove_descendants(child)
    node.children.clear()


def count_descendants(node: "RepertoireNode") -> int:
    """Count all descendant nodes below the given node."""
    total = 0
    for child in node.children:
        total += 1 + count_descendants(child)
    return total


def count_nodes(node: "RepertoireNode") -> int:
    """Count the total number of nodes in a subtree (including the root)."""
    total = 1
    for child in node.children:
        total += count_nodes(child)
    return total


def collect_terminal_paths(
    start: "RepertoireNode",
    *,
    follow_best: bool = False,
    stop_on_termination: bool = False,
) -> list[list["RepertoireNode"]]:
    """Collect full paths from the start node to all terminals."""

    paths: list[list["RepertoireNode"]] = []

    def _walk(node: "RepertoireNode", path: list["RepertoireNode"]) -> None:
        path.append(node)

        if stop_on_termination and getattr(node, "termination_reason", None):
            paths.append(list(path))
            path.pop()
            return

        children = getattr(node, "children", [])
        if not children:
            paths.append(list(path))
            path.pop()
            return

        if follow_best and getattr(node, "is_player_turn", False):
            best_child = getattr(node, "best_child", None)
            if best_child is not None:
                next_children = [best_child]
            elif children:
                next_children = [children[0]]
            else:
                next_children = []
        else:
            next_children = list(children)

        for child in next_children:
            _walk(child, path)

        path.pop()

    _walk(start, [])
    return paths


def collect_terminal_nodes(
    start: "RepertoireNode",
    *,
    follow_best: bool = False,
    stop_on_termination: bool = False,
) -> list["RepertoireNode"]:
    """Collect terminal nodes under the start node."""
    return [
        path[-1]
        for path in collect_terminal_paths(
            start, follow_best=follow_best, stop_on_termination=stop_on_termination
        )
    ]


def calculate_path_probability(
    path: Sequence["RepertoireNode"], *, assume_uniform_if_missing: bool = False
) -> float:
    """Calculate cumulative probability of reaching a node given a path."""
    probability = 1.0

    for idx in range(1, len(path)):
        node = path[idx]
        parent = path[idx - 1]

        if not node.is_player_turn:
            if not assume_uniform_if_missing:
                stats = getattr(node, "stats", None)
                if not stats or stats.total_games <= 0:
                    continue

            siblings = getattr(parent, "children", [])
            if len(siblings) <= 1:
                continue

            total = 0
            child_weight = None
            for sibling in siblings:
                if sibling.stats and sibling.stats.total_games > 0:
                    weight = sibling.stats.total_games
                elif assume_uniform_if_missing:
                    weight = 1
                else:
                    weight = 0

                total += weight
                if sibling is node:
                    child_weight = weight

            if total > 0 and child_weight is not None:
                probability *= child_weight / total
            elif assume_uniform_if_missing and siblings:
                probability *= 1.0 / len(siblings)

    return probability


def iter_terminal_probabilities(
    start: "RepertoireNode",
    *,
    follow_best: bool = False,
    stop_on_termination: bool = False,
    assume_uniform_if_missing: bool = False,
) -> list[tuple["RepertoireNode", float]]:
    """Collect terminal nodes paired with their reach probabilities."""
    return [
        (
            path[-1],
            calculate_path_probability(
                path, assume_uniform_if_missing=assume_uniform_if_missing
            ),
        )
        for path in collect_terminal_paths(
            start,
            follow_best=follow_best,
            stop_on_termination=stop_on_termination,
        )
    ]


def path_to_moves(path: Sequence["RepertoireNode"]) -> str:
    """Convert a node path to SAN move string."""
    moves = []
    for node in path[1:]:
        move_san = getattr(node, "move_san", None)
        if move_san:
            moves.append(move_san)
    return " ".join(moves) if moves else "Starting position"

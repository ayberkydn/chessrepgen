from __future__ import annotations

from dataclasses import dataclass, field

import chess

from .stats import MoveStats


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
    terminal_advantage: float | None = None

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
    terminal_advantage: float | None = None
    pruned_alternative_scores: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class RepertoireLine:
    """Represents a fully constructed repertoire line rooted at a position."""

    initial_moves: str
    root: RepertoireNode

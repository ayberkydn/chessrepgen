"""Stockfish evaluation service for terminal nodes."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import chess
import chess.engine

if TYPE_CHECKING:
    from models.graph import RepertoireNode

from .cache import StockfishCache

logger = logging.getLogger(__name__)


class StockfishEvaluator:
    """Evaluates chess positions using Stockfish engine."""

    def __init__(self, config, is_white: bool):
        self.config = config
        self.is_white = is_white
        self.engine: chess.engine.SimpleEngine | None = None
        cache_path = getattr(config, "stockfish_cache_file", "stockfish_cache.db")
        self.cache = StockfishCache(cache_path)

    def _start_engine(self) -> None:
        """Start the Stockfish engine."""
        if self.engine is not None:
            return
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(
                self.config.stockfish_path
            )
            self.engine.configure({"Threads": self.config.stockfish_threads})
            logger.info(
                "Stockfish engine started (depth=%d, threads=%d)",
                self.config.stockfish_depth,
                self.config.stockfish_threads,
            )
        except Exception as e:
            logger.error("Failed to start Stockfish engine: %s", e)
            raise

    def _stop_engine(self) -> None:
        """Stop the Stockfish engine."""
        if self.engine is not None:
            self.engine.quit()
            self.engine = None

    def evaluate_position(self, board: chess.Board) -> float | None:
        """
        Evaluate a position and return a score normalized to [-1, 1].

        Returns the score from the perspective of the repertoire player.
        Positive = good for player, Negative = bad for player.
        """
        fen = board.fen()
        target_depth = getattr(self.config, "stockfish_depth", 0)

        cached = self.cache.get_stockfish_evaluation(fen)
        if cached and cached["depth"] >= target_depth:
            white_score = cached["white_score"]
            return white_score if self.is_white else -white_score

        if self.engine is None:
            return None
        try:
            info = self.engine.analyse(board, chess.engine.Limit(depth=target_depth))
            score = info.get("score")
            if score is None:
                return None

            # Get score from white's perspective
            pov_score = score.white()

            # Handle mate scores
            if pov_score.is_mate():
                mate_in = pov_score.mate()
                # Normalize mate scores: mate in N moves -> ±1.0
                # Closer mates are still ±1.0, we just indicate winning/losing
                if mate_in is not None and mate_in > 0:
                    white_score = 1.0  # White is winning
                else:
                    white_score = -1.0  # Black is winning
            else:
                # Convert centipawns to normalized score [-1, 1]
                # Using a sigmoid-like transformation
                # 100 centipawns (1 pawn) ~ 0.2, 500 cp ~ 0.7
                cp = pov_score.score()
                if cp is None:
                    return None
                # Normalize: tanh(cp / 400) gives reasonable scaling
                import math

                white_score = math.tanh(cp / 400.0)

            self.cache.set_stockfish_evaluation(fen, target_depth, white_score)

            # Convert to player's perspective
            if self.is_white:
                return white_score
            else:
                return -white_score

        except Exception as e:
            logger.warning("Failed to evaluate position: %s", e)
            return None

    def evaluate_terminal_nodes(self, roots: list[RepertoireNode]) -> None:
        """
        Evaluate all terminal nodes in the repertoire using Stockfish.

        Terminal nodes are nodes with no edges (leaf nodes in the DAG).
        Shows progress indicator during evaluation.
        """
        if not getattr(self.config, "use_stockfish", False):
            logger.info("Stockfish evaluation disabled in config")
            return

        # Collect all terminal nodes (nodes with no edges)
        terminal_nodes: list[RepertoireNode] = []
        visited: set[str] = set()

        def collect_terminals(node: RepertoireNode) -> None:
            if node.key in visited:
                return
            visited.add(node.key)

            if not node.edges:
                terminal_nodes.append(node)
            else:
                for edge in node.edges:
                    if edge.child:
                        collect_terminals(edge.child)

        for root in roots:
            collect_terminals(root)

        total = len(terminal_nodes)
        if total == 0:
            logger.info("No terminal nodes to evaluate")
            return

        logger.info("Starting Stockfish evaluation of %d terminal positions", total)

        try:
            self._start_engine()

            for i, node in enumerate(terminal_nodes, 1):
                # Progress indicator
                sys.stdout.write(f"\r{i}/{total} positions analyzed")
                sys.stdout.flush()

                score = self.evaluate_position(node.board)
                node.stockfish_score = score

            # Final newline after progress
            sys.stdout.write("\n")
            sys.stdout.flush()

            logger.info("Stockfish evaluation complete: %d positions analyzed", total)

        finally:
            self._stop_engine()

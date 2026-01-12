from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import chess
import chess.pgn

from .stats import calculate_padding, total_games

logger = logging.getLogger(__name__)


def extract_and_format_stats_comment(edge, is_white: bool, config=None) -> str:
    """Extract win/draw/black statistics and format them for PGN comments.

    Returns minified comment like: A:5.0,T:10.0,P:25.0%,G:1500,Alts:Nf3 4.5,d4 3.2
    """
    parts = []

    if edge.stats:
        padding_ratio = getattr(config, "padding_ratio", 0.02) if config else 0.02
        static_padding = getattr(config, "static_padding", 0) if config else 0

        if edge.parent and edge.parent.position_stats:
            lichess_stats = edge.parent.position_stats.get("lichess")
            parent_games = total_games(lichess_stats)
        else:
            parent_games = 0

        padding = calculate_padding(parent_games, padding_ratio, static_padding)

        advantage = edge.stats.advantage(
            is_white,
            padding_strength=padding,
        )
        parts.append(f"A:{advantage * 100:.1f}")

    # Get terminal advantage from child or from edge (for pruned nodes)
    child_advantage = (
        getattr(edge.child, "terminal_advantage", None) if edge.child else None
    )
    if child_advantage is None:
        child_advantage = getattr(edge, "terminal_advantage", None)

    if child_advantage is not None:
        parts.append(f"T:{child_advantage * 100:.1f}")

    if edge.stats and edge.parent and edge.parent.position_stats:
        lichess_stats = edge.parent.position_stats.get("lichess")
        if lichess_stats:
            parent_total = (
                lichess_stats.get("white", 0)
                + lichess_stats.get("draws", 0)
                + lichess_stats.get("black", 0)
            )
            if parent_total > 0:
                popularity = edge.stats.total_games / parent_total
                parts.append(f"P:{popularity * 100:.1f}%")
                parts.append(f"G:{edge.stats.total_games}")

    alternative_scores = getattr(edge, "pruned_alternative_scores", None) or []
    # Limit to top 3 alternatives
    alt_parts = [
        f"{san} {score * 100:.1f}"
        for san, score in alternative_scores[:3]
        if score is not None
    ]
    if alt_parts:
        parts.append(f"Alts:{','.join(alt_parts)}")

    return ",".join(parts)


def _slug_initial_moves(moves: str, fallback: str) -> str:
    """Create a filesystem-friendly label from an initial move string."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", moves.strip()).strip("-").lower()
    return slug or fallback


class PGNWriter:
    def __init__(self, config, side: str = "white"):
        self.config = config
        self.is_white = side == "white"

    def node_to_pgn_variation(
        self, node, game_node: chess.pgn.GameNode, is_main_line: bool = True
    ) -> None:
        if not node.edges:
            # This is a terminal node - only include formatted statistics for parent edge
            # Skip all termination reasons and other comments
            return

        # Sort moves differently based on whose turn it is:
        # - Player moves: Sort by terminal advantage (best for repertoire player)
        # - Opponent moves: Sort by popularity (most common opponent responses)

        # Log any edges with None terminal advantages for debugging (player moves only)
        if node.is_player_turn:
            for edge in node.edges:
                child_twm = (
                    getattr(edge.child, "terminal_advantage", None)
                    if edge.child
                    else None
                )
                edge_twm = getattr(edge, "terminal_advantage", None)
                if child_twm is None and edge_twm is None:
                    logger.debug(
                        "PGN_SORT: Player edge has None terminal advantage. "
                        "Move: %s, Child exists: %s, Edge stats available: %s, "
                        "Node FEN: %s, Edge is terminal: %s",
                        edge.move_san,
                        edge.child is not None,
                        edge.stats is not None if edge.stats else False,
                        node.board.fen(),
                        edge.is_terminal,
                    )

        if node.is_player_turn:
            # Player moves: Sort by terminal advantage (descending), then by popularity
            sorted_edges = sorted(
                node.edges,
                key=lambda e: (
                    # Get terminal advantage from child or edge (for pruned nodes), default to -1 for None
                    (
                        (
                            getattr(e.child, "terminal_advantage", None)
                            if e.child
                            else None
                        )
                        or getattr(e, "terminal_advantage", None)
                    )
                    or -1,
                    e.stats.total_games if e.stats else 0,
                ),
                reverse=True,
            )
        else:
            # Opponent moves: Sort by popularity (total games) descending
            sorted_edges = sorted(
                node.edges,
                key=lambda e: e.stats.total_games if e.stats else 0,
                reverse=True,
            )

        for i, edge in enumerate(sorted_edges):
            if edge.move:
                if i == 0 and is_main_line:
                    new_node = game_node.add_main_variation(edge.move)
                else:
                    new_node = game_node.add_variation(edge.move)

                # Always include formatted statistics as comments
                stats_comment = extract_and_format_stats_comment(
                    edge, self.is_white, self.config
                )
                if stats_comment:
                    new_node.comment = stats_comment

                if edge.is_terminal:
                    continue

                self.node_to_pgn_variation(edge.child, new_node, is_main_line=(i == 0))

    def create_pgn_game(self, root_node, initial_moves_str: str) -> chess.pgn.Game:
        game = chess.pgn.Game()

        game.headers["Event"] = "Chess Repertoire"
        game.headers["Site"] = "Generated from Lichess data"
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        game.headers["Round"] = "?"
        game.headers["White"] = "Repertoire" if self.is_white else "Opponent"
        game.headers["Black"] = "Opponent" if self.is_white else "Repertoire"
        game.headers["Result"] = "*"

        game.headers["Annotator"] = "Chess Repertoire Generator"
        game.headers["RepertoireSide"] = "white" if self.is_white else "black"
        game.headers["InitialMoves"] = initial_moves_str
        game.headers["TimeControl"] = ", ".join(self.config.time_control)
        game.headers["RatingBrackets"] = ", ".join(map(str, self.config.ratings))

        board = chess.Board()
        game_node = game

        initial_moves = initial_moves_str.strip().split()
        for i, move_str in enumerate(initial_moves):
            try:
                move = board.parse_san(move_str)
            except (
                chess.InvalidMoveError,
                chess.IllegalMoveError,
                chess.AmbiguousMoveError,
                ValueError,
            ):
                try:
                    move = chess.Move.from_uci(move_str)
                except ValueError:
                    logger.error(f"Could not parse initial move: {move_str}")
                    continue

            board.push(move)
            game_node = game_node.add_main_variation(move)

            # Add terminal advantage comment to the last initial move
            is_last_initial_move = i == len(initial_moves) - 1
            if is_last_initial_move:
                if root_node.terminal_advantage is not None:
                    game_node.comment = f"T:{root_node.terminal_advantage * 100:.1f}"
                else:
                    logger.debug(
                        "Root node has no terminal advantage for initial moves: %s",
                        initial_moves_str,
                    )

        self.node_to_pgn_variation(root_node, game_node)

        return game

    def write_repertoire(
        self, roots: list, output_path: str, initial_moves: list[str] | None = None
    ) -> list[str]:
        if initial_moves is None:
            # Fallback for backward compatibility
            initial_moves = getattr(
                self.config,
                "initial_moves_white" if self.is_white else "initial_moves_black",
                [],
            )

        base_path = Path(output_path)
        suffix = base_path.suffix or ".pgn"
        parent = base_path.parent

        output_paths: list[str] = []
        for i, root in enumerate(roots):
            initial_moves_str = (
                initial_moves[i] if initial_moves and i < len(initial_moves) else ""
            )
            game = self.create_pgn_game(root, initial_moves_str)

            # Generate filename based on side and initial moves
            # If initial_moves_str is empty, just use side (e.g., "white.pgn", "black.pgn")
            # Otherwise concatenate moves without separator (e.g., "white_e4e5.pgn")
            side_prefix = "white" if self.is_white else "black"
            if initial_moves_str:
                label = _slug_initial_moves(initial_moves_str, fallback=f"line-{i + 1}")
                filename = f"{side_prefix}_{label}{suffix}"
            else:
                filename = f"{side_prefix}{suffix}"

            path = parent / filename
            # Use FileExporter for proper line wrapping (< 80 chars per line)
            # This ensures PGN files comply with the specification
            with open(path, "w", encoding="utf-8") as f:
                exporter = chess.pgn.FileExporter(f)
                game.accept(exporter)
            output_paths.append(str(path))

        logger.info("Generated %d repertoire file(s)", len(output_paths))
        if output_paths:
            logger.info("PGN files: %s", ", ".join(output_paths))
        return output_paths

    def get_statistics_summary(
        self, roots: list, initial_moves: list[str] | None = None
    ) -> str:
        if initial_moves is None:
            # Fallback for backward compatibility
            initial_moves = getattr(
                self.config,
                "initial_moves_white" if self.is_white else "initial_moves_black",
                [],
            )

        total_positions = 0
        total_variations = 0
        max_depth_reached = 0

        def count_nodes(node, depth=0):
            nonlocal total_positions, total_variations, max_depth_reached

            total_positions += 1
            max_depth_reached = max(max_depth_reached, depth)

            if len(node.edges) > 1:
                total_variations += len(node.edges) - 1

            for edge in node.edges:
                if edge.is_terminal:
                    continue
                count_nodes(edge.child, depth + 1)

        for root in roots:
            count_nodes(root)

        # Build initial moves summary
        initial_moves_summary = "\nInitial Moves Summary:\n----------------------\n"
        for i, root in enumerate(roots):
            initial_moves_str = (
                initial_moves[i] if initial_moves and i < len(initial_moves) else "?"
            )
            terminal_adv = root.terminal_advantage
            if terminal_adv is not None:
                terminal_adv_pct = terminal_adv * 100
                initial_moves_summary += f"{i + 1}. {initial_moves_str}: Terminal Advantage: {terminal_adv_pct:+.2f}%\n"
            else:
                initial_moves_summary += (
                    f"{i + 1}. {initial_moves_str}: Terminal Advantage: N/A\n"
                )

        summary = f"""
Repertoire Statistics:
----------------------{initial_moves_summary}
Overall Statistics:
Total positions analyzed: {total_positions}
Total variations: {total_variations}
Maximum depth reached: {max_depth_reached}
Configuration:
  Side: {"white" if self.is_white else "black"}
  Rating brackets: {", ".join(map(str, self.config.ratings))}
  Time controls: {", ".join(self.config.time_control)}
  Min opponent popularity: {self.config.min_opponent_popularity:.1%}
"""

        return summary

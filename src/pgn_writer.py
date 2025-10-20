import chess
import chess.pgn
import logging

from datetime import datetime
from io import StringIO


logger = logging.getLogger(__name__)


class PGNWriter:
    def __init__(self, config, side: str = "white"):
        self.config = config
        self.is_white = side == "white"
        self.include_comments = getattr(config, "include_comments", True)

    def _ensure_terminal_annotations(self, node) -> None:
        """Ensure every terminal node carries a termination reason comment."""

        def visit(current):
            if not current.children:
                reason = current.termination_reason
                if not reason:
                    if current.is_player_turn:
                        reason = (
                            f"[TRUNCATED] Player continuation not analyzed "
                            f"(depth limit: {self.config.depth})"
                        )
                    else:
                        reason = (
                            f"[TRUNCATED] Opponent continuation not analyzed "
                            f"(depth limit: {self.config.depth})"
                        )
                    current.termination_reason = reason

                if self.include_comments and reason:
                    comment = current.comment or ""
                    if reason not in comment:
                        if comment:
                            current.comment = f"{comment} | {reason}"
                        else:
                            current.comment = reason
                return

            for child in current.children:
                visit(child)

        visit(node)

    def node_to_pgn_variation(
        self, node, game_node: chess.pgn.GameNode, is_main_line: bool = True
    ) -> None:
        if not node.children:
            # This is a terminal node - add termination reason if present
            if self.include_comments:
                reason = node.termination_reason
                existing_comment = game_node.comment or node.comment or ""

                if reason:
                    if existing_comment:
                        if reason not in existing_comment:
                            game_node.comment = f"{existing_comment} | {reason}"
                        else:
                            game_node.comment = existing_comment
                    else:
                        game_node.comment = reason
                elif existing_comment:
                    game_node.comment = existing_comment
            return

        for i, child in enumerate(node.children):
            if child.move:
                if i == 0 and is_main_line:
                    new_node = game_node.add_main_variation(child.move)
                else:
                    new_node = game_node.add_variation(child.move)

                if self.include_comments and child.comment:
                    new_node.comment = child.comment

                self.node_to_pgn_variation(child, new_node, is_main_line=(i == 0))

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
        game.headers["Depth"] = str(self.config.depth)

        board = chess.Board()
        game_node = game

        initial_moves = initial_moves_str.strip().split()
        for move_str in initial_moves:
            try:
                move = board.parse_san(move_str)
            except:
                try:
                    move = chess.Move.from_uci(move_str)
                except:
                    logger.error(f"Could not parse initial move: {move_str}")
                    continue

            board.push(move)
            game_node = game_node.add_main_variation(move)

        self.node_to_pgn_variation(root_node, game_node)

        return game

    def write_repertoire(
        self, roots: list, output_path: str, initial_moves: list[str] | None = None
    ):
        if initial_moves is None:
            # Fallback for backward compatibility
            initial_moves = getattr(
                self.config,
                "initial_moves_white" if self.is_white else "initial_moves_black",
                [],
            )

        all_games = []

        for i, root in enumerate(roots):
            initial_moves_str = (
                initial_moves[i] if initial_moves and i < len(initial_moves) else ""
            )
            self._ensure_terminal_annotations(root)
            game = self.create_pgn_game(root, initial_moves_str)
            all_games.append(game)

        with open(output_path, "w") as f:
            for i, game in enumerate(all_games):
                if i > 0:
                    f.write("\n\n")
                f.write(str(game))

        logger.info(f"Repertoire written to {output_path}")
        logger.info(f"Generated {len(all_games)} repertoire(s)")

    def get_statistics_summary(
        self, roots: list, initial_moves: list[str] | None = None
    ) -> str:
        total_positions = 0
        total_variations = 0
        max_depth_reached = 0

        def count_nodes(node, depth=0):
            nonlocal total_positions, total_variations, max_depth_reached

            total_positions += 1
            max_depth_reached = max(max_depth_reached, depth)

            if len(node.children) > 1:
                total_variations += len(node.children) - 1

            for child in node.children:
                count_nodes(child, depth + 1)

        for root in roots:
            count_nodes(root)

        summary = f"""
Repertoire Statistics:
----------------------
Total positions analyzed: {total_positions}
Total variations: {total_variations}
Maximum depth reached: {max_depth_reached}
Configuration:
  Side: {"white" if self.is_white else "black"}
  Target depth: {self.config.depth}
  Rating brackets: {", ".join(map(str, self.config.ratings))}
  Time controls: {", ".join(self.config.time_control)}
  Min opponent popularity: {self.config.min_opponent_popularity:.1%}
  Min high-rating popularity: {self.config.min_highrating_popularity:.1%}
"""

        return summary

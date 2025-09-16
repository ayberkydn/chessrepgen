import chess
import chess.pgn
import logging
from typing import List, Optional
from datetime import datetime
from io import StringIO

logger = logging.getLogger(__name__)


class PGNWriter:
    def __init__(self, config):
        self.config = config
        self.is_white = config.side == "white"
    
    def node_to_pgn_variation(
        self,
        node,
        game_node: chess.pgn.GameNode,
        is_main_line: bool = True
    ) -> None:
        
        if not node.children:
            # This is a terminal node - add termination reason if present
            if node.termination_reason:
                # Add termination reason as a comment
                if game_node.comment:
                    game_node.comment = f"{game_node.comment} | {node.termination_reason}"
                else:
                    game_node.comment = f"[{node.termination_reason}]"
            elif node.comment:
                game_node.comment = node.comment
            return
        
        for i, child in enumerate(node.children):
            if child.move:
                if i == 0 and is_main_line:
                    new_node = game_node.add_main_variation(child.move)
                else:
                    new_node = game_node.add_variation(child.move)
                
                if child.comment:
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
        game.headers["RepertoireSide"] = self.config.side
        game.headers["InitialMoves"] = initial_moves_str
        game.headers["TimeControl"] = ", ".join(self.config.time_control)
        game.headers["RatingRange"] = f"{self.config.min_rating}-{self.config.max_rating}"
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
    
    def write_repertoire(self, roots: List, output_path: str):
        
        all_games = []
        
        for i, root in enumerate(roots):
            initial_moves_str = self.config.initial_moves[i] if i < len(self.config.initial_moves) else ""
            game = self.create_pgn_game(root, initial_moves_str)
            all_games.append(game)
        
        with open(output_path, 'w') as f:
            for i, game in enumerate(all_games):
                if i > 0:
                    f.write("\n\n")
                f.write(str(game))
        
        logger.info(f"Repertoire written to {output_path}")
        logger.info(f"Generated {len(all_games)} repertoire(s)")
    
    def get_statistics_summary(self, roots: List) -> str:
        
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
  Side: {self.config.side}
  Target depth: {self.config.depth}
  Rating range: {self.config.min_rating}-{self.config.max_rating}
  Time controls: {', '.join(self.config.time_control)}
  Min popularity: {self.config.min_popularity:.1%}
  Min master popularity: {self.config.min_master_popularity:.1%}
"""
        
        return summary
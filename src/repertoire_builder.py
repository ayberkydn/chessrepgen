import logging
import chess
import chess.pgn
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from lichess_client import LichessClient
from cache import ChessCache
from evaluator import MoveEvaluator, MoveStats

logger = logging.getLogger(__name__)


@dataclass
class RepertoireNode:
    board: chess.Board
    move: Optional[chess.Move]
    move_san: Optional[str]
    stats: Optional[MoveStats]
    depth: int
    is_player_turn: bool
    termination_reason: Optional[str]
    children: List['RepertoireNode']
    comment: str = ""
    
    def add_child(self, child: 'RepertoireNode'):
        self.children.append(child)


class RepertoireBuilder:
    def __init__(self, config):
        self.config = config
        self.client = LichessClient()
        self.cache = ChessCache(config.cache_file, config.cache_expiry_days)
        self.evaluator = MoveEvaluator(config)
        self.is_white = config.side == "white"
        self.visited_positions: Set[str] = set()
    
    def parse_initial_moves(self, moves_str: str) -> List[chess.Move]:
        board = chess.Board()
        moves = []
        
        move_parts = moves_str.strip().split()
        for move_str in move_parts:
            try:
                move = board.parse_san(move_str)
                moves.append(move)
                board.push(move)
            except:
                try:
                    move = chess.Move.from_uci(move_str)
                    if move in board.legal_moves:
                        moves.append(move)
                        board.push(move)
                    else:
                        logger.error(f"Illegal move: {move_str}")
                        raise ValueError(f"Illegal move: {move_str}")
                except:
                    logger.error(f"Invalid move format: {move_str}")
                    raise ValueError(f"Invalid move format: {move_str}")
        
        return moves
    
    def get_position_data(self, fen: str) -> Dict:
        cached_master = self.cache.get_master_stats(fen)
        cached_lichess = self.cache.get_lichess_stats(
            fen, 
            self.config.min_rating,
            self.config.max_rating,
            self.config.time_control
        )
        
        if cached_master and cached_lichess:
            return {
                "master": cached_master,
                "lichess": cached_lichess
            }
        
        api_data = self.client.get_position_stats(
            fen,
            self.config.min_rating,
            self.config.max_rating,
            self.config.time_control
        )
        
        if not cached_master and api_data["master"]:
            self.cache.set_master_stats(fen, api_data["master"])
        
        if not cached_lichess and api_data["lichess"]:
            self.cache.set_lichess_stats(
                fen,
                api_data["lichess"],
                self.config.min_rating,
                self.config.max_rating,
                self.config.time_control
            )
        
        return {
            "master": cached_master or api_data["master"],
            "lichess": cached_lichess or api_data["lichess"]
        }
    
    def build_node(
        self,
        board: chess.Board,
        depth: int,
        move: Optional[chess.Move] = None,
        move_san: Optional[str] = None,
        stats: Optional[MoveStats] = None
    ) -> Optional[RepertoireNode]:
        
        fen = board.fen()
        
        if fen in self.visited_positions:
            logger.debug(f"Position already visited: {fen[:20]}...")
            return None
        
        self.visited_positions.add(fen)
        
        is_player_turn = (board.turn == chess.WHITE) == self.is_white
        
        node = RepertoireNode(
            board=board.copy(),
            move=move,
            move_san=move_san,
            stats=stats,
            depth=depth,
            is_player_turn=is_player_turn,
            termination_reason=None,
            children=[]
        )
        
        if board.is_game_over():
            result = board.result()
            node.termination_reason = f"Game over: {result}"
            node.comment = f"Game ends: {result}"
            return node
        
        position_data = self.get_position_data(fen)
        master_data = position_data["master"]
        lichess_data = position_data["lichess"]
        
        should_stop, reason = self.evaluator.should_terminate(
            depth, master_data, lichess_data
        )
        
        if should_stop:
            node.termination_reason = reason
            node.comment = reason
            return node
        
        candidate_moves = self.evaluator.evaluate_position(
            master_data, lichess_data, is_player_turn
        )
        
        if not candidate_moves:
            node.termination_reason = "No candidate moves found"
            node.comment = "No suitable moves meet the criteria"
            return node
        
        for move_stats in candidate_moves:
            try:
                child_board = board.copy()
                move = chess.Move.from_uci(move_stats.uci)
                
                if move not in child_board.legal_moves:
                    logger.warning(f"Illegal move from API: {move_stats.uci}")
                    continue
                
                san = child_board.san(move)
                child_board.push(move)
                
                child_node = self.build_node(
                    child_board,
                    depth + 1,
                    move,
                    san,
                    move_stats
                )
                
                if child_node:
                    score = move_stats.expected_score(self.is_white)
                    popularity = move_stats.popularity
                    # Add statistics to comment, but preserve termination reason if present
                    stats_comment = f"Score: {score:.1%}, Games: {int(popularity)}"
                    if child_node.termination_reason:
                        child_node.comment = f"{stats_comment} | {child_node.termination_reason}"
                    else:
                        child_node.comment = stats_comment
                    node.add_child(child_node)
                    
            except Exception as e:
                logger.error(f"Error processing move {move_stats.uci}: {e}")
                continue
        
        return node
    
    def build_repertoire(self) -> List[RepertoireNode]:
        roots = []
        
        for initial_moves_str in self.config.initial_moves:
            logger.info(f"Building repertoire for: {initial_moves_str}")
            
            try:
                board = chess.Board()
                initial_moves = self.parse_initial_moves(initial_moves_str)
                
                for move in initial_moves:
                    board.push(move)
                
                root = self.build_node(board, 0)
                if root:
                    roots.append(root)
                    
            except Exception as e:
                logger.error(f"Error building repertoire for {initial_moves_str}: {e}")
                continue
        
        return roots
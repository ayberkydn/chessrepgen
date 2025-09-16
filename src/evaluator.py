import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MoveStats:
    uci: str
    san: str
    white_wins: int
    draws: int
    black_wins: int
    total_games: int
    
    @property
    def popularity(self) -> float:
        return self.total_games
    
    @property
    def expected_score_white(self) -> float:
        if self.total_games == 0:
            return 0.5
        return (self.white_wins + 0.5 * self.draws) / self.total_games
    
    @property
    def expected_score_black(self) -> float:
        if self.total_games == 0:
            return 0.5
        return (self.black_wins + 0.5 * self.draws) / self.total_games
    
    def expected_score(self, for_white: bool) -> float:
        return self.expected_score_white if for_white else self.expected_score_black


class MoveEvaluator:
    def __init__(self, config):
        self.config = config
        self.is_white = config.side == "white"
    
    def parse_move_data(self, move_data: Dict, total_games: int) -> MoveStats:
        return MoveStats(
            uci=move_data.get("uci", ""),
            san=move_data.get("san", ""),
            white_wins=move_data.get("white", 0),
            draws=move_data.get("draws", 0),
            black_wins=move_data.get("black", 0),
            total_games=move_data.get("white", 0) + move_data.get("draws", 0) + move_data.get("black", 0)
        )
    
    def evaluate_position(
        self,
        master_data: Optional[Dict],
        lichess_data: Optional[Dict],
        is_player_turn: bool
    ) -> List[MoveStats]:
        
        moves = []
        
        if is_player_turn and lichess_data and lichess_data.get("moves"):
            # For player moves: filter by master popularity, but use Lichess data for expected score
            total_lichess_games = (
                lichess_data.get("white", 0) + 
                lichess_data.get("draws", 0) + 
                lichess_data.get("black", 0)
            )
            
            # Build a set of moves that meet master popularity threshold
            master_popular_moves = set()
            if master_data and master_data.get("moves"):
                total_master_games = (
                    master_data.get("white", 0) + 
                    master_data.get("draws", 0) + 
                    master_data.get("black", 0)
                )
                for move_data in master_data["moves"]:
                    if total_master_games > 0:
                        move_popularity = (move_data.get("white", 0) + move_data.get("draws", 0) + move_data.get("black", 0)) / total_master_games
                        if move_popularity >= self.config.min_master_popularity:
                            master_popular_moves.add(move_data.get("uci", ""))
            
            # Now evaluate moves from Lichess data that are also popular in master games
            for move_data in lichess_data["moves"]:
                uci = move_data.get("uci", "")
                if uci in master_popular_moves:
                    move_stats = self.parse_move_data(move_data, total_lichess_games)
                    moves.append(move_stats)
            
            # Sort by expected score from Lichess data
            moves.sort(key=lambda m: m.expected_score(self.is_white), reverse=True)
            
            # For player's repertoire: return only THE BEST move
            if moves:
                return [moves[0]]  # Only one move for the repertoire side
        
        elif not is_player_turn:
            combined_moves = {}
            
            if master_data and master_data.get("moves"):
                total_master = (
                    master_data.get("white", 0) + 
                    master_data.get("draws", 0) + 
                    master_data.get("black", 0)
                )
                for move_data in master_data["moves"]:
                    uci = move_data.get("uci", "")
                    if uci:
                        combined_moves[uci] = self.parse_move_data(move_data, total_master)
            
            if lichess_data and lichess_data.get("moves"):
                total_lichess = (
                    lichess_data.get("white", 0) + 
                    lichess_data.get("draws", 0) + 
                    lichess_data.get("black", 0)
                )
                
                for move_data in lichess_data["moves"]:
                    uci = move_data.get("uci", "")
                    if uci:
                        if uci in combined_moves:
                            existing = combined_moves[uci]
                            new_stats = self.parse_move_data(move_data, total_lichess)
                            combined_moves[uci] = MoveStats(
                                uci=uci,
                                san=existing.san or new_stats.san,
                                white_wins=existing.white_wins + new_stats.white_wins,
                                draws=existing.draws + new_stats.draws,
                                black_wins=existing.black_wins + new_stats.black_wins,
                                total_games=existing.total_games + new_stats.total_games
                            )
                        else:
                            combined_moves[uci] = self.parse_move_data(move_data, total_lichess)
            
            total_all_games = sum(m.total_games for m in combined_moves.values())
            
            if total_all_games > 0:
                for move in combined_moves.values():
                    popularity = move.total_games / total_all_games
                    if popularity >= self.config.min_popularity:
                        moves.append(move)
            
            moves.sort(key=lambda m: m.total_games, reverse=True)
            return moves[:10]
        
        return moves
    
    def should_terminate(
        self,
        depth: int,
        master_data: Optional[Dict],
        lichess_data: Optional[Dict]
    ) -> Tuple[bool, str]:
        
        if depth >= self.config.depth:
            return True, f"Maximum depth {self.config.depth} reached"
        
        # Master games are used as quality threshold for termination
        if master_data:
            total_master = (
                master_data.get("white", 0) + 
                master_data.get("draws", 0) + 
                master_data.get("black", 0)
            )
            if total_master < self.config.min_master_games:
                return True, f"Insufficient master games ({total_master} < {self.config.min_master_games})"
        else:
            return True, "No master games data available"
        
        # Lichess games must have sufficient data for statistics
        if lichess_data:
            total_lichess = (
                lichess_data.get("white", 0) + 
                lichess_data.get("draws", 0) + 
                lichess_data.get("black", 0)
            )
            if total_lichess < 1000:
                return True, f"Insufficient Lichess games ({total_lichess} < 1000)"
        else:
            return True, "No Lichess games data available"
        
        return False, ""
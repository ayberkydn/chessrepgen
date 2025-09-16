import sqlite3
import json
import time
import logging
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ChessCache:
    def __init__(self, db_path: str, expiry_days: int = 30):
        self.db_path = db_path
        self.expiry_seconds = expiry_days * 24 * 60 * 60
        self._init_db()
    
    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS master_stats (
                    fen TEXT PRIMARY KEY,
                    data TEXT,
                    timestamp INTEGER
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS lichess_stats (
                    fen TEXT,
                    rating_range TEXT,
                    time_control TEXT,
                    data TEXT,
                    timestamp INTEGER,
                    PRIMARY KEY (fen, rating_range, time_control)
                )
            ''')
            
            conn.execute('CREATE INDEX IF NOT EXISTS idx_master_fen ON master_stats(fen)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_lichess_fen ON lichess_stats(fen)')
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def _is_expired(self, timestamp: int) -> bool:
        return (time.time() - timestamp) > self.expiry_seconds
    
    def get_master_stats(self, fen: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT data, timestamp FROM master_stats WHERE fen = ?',
                (fen,)
            )
            row = cursor.fetchone()
            
            if row:
                data, timestamp = row
                if not self._is_expired(timestamp):
                    logger.debug(f"Cache hit for master stats: {fen}")
                    return json.loads(data)
                else:
                    logger.debug(f"Cache expired for master stats: {fen}")
            
            return None
    
    def set_master_stats(self, fen: str, data: Dict):
        with self._get_connection() as conn:
            conn.execute(
                '''INSERT OR REPLACE INTO master_stats (fen, data, timestamp) 
                   VALUES (?, ?, ?)''',
                (fen, json.dumps(data), int(time.time()))
            )
            conn.commit()
            logger.debug(f"Cached master stats for: {fen}")
    
    def get_lichess_stats(
        self, 
        fen: str, 
        min_rating: int,
        max_rating: int,
        time_controls: List[str]
    ) -> Optional[Dict]:
        rating_range = f"{min_rating}-{max_rating}"
        time_control_str = ",".join(sorted(time_controls))
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                '''SELECT data, timestamp FROM lichess_stats 
                   WHERE fen = ? AND rating_range = ? AND time_control = ?''',
                (fen, rating_range, time_control_str)
            )
            row = cursor.fetchone()
            
            if row:
                data, timestamp = row
                if not self._is_expired(timestamp):
                    logger.debug(f"Cache hit for lichess stats: {fen}")
                    return json.loads(data)
                else:
                    logger.debug(f"Cache expired for lichess stats: {fen}")
            
            return None
    
    def set_lichess_stats(
        self, 
        fen: str, 
        data: Dict,
        min_rating: int,
        max_rating: int,
        time_controls: List[str]
    ):
        rating_range = f"{min_rating}-{max_rating}"
        time_control_str = ",".join(sorted(time_controls))
        
        with self._get_connection() as conn:
            conn.execute(
                '''INSERT OR REPLACE INTO lichess_stats 
                   (fen, rating_range, time_control, data, timestamp) 
                   VALUES (?, ?, ?, ?, ?)''',
                (fen, rating_range, time_control_str, json.dumps(data), int(time.time()))
            )
            conn.commit()
            logger.debug(f"Cached lichess stats for: {fen}")
    
    def clear_expired(self):
        cutoff_time = time.time() - self.expiry_seconds
        
        with self._get_connection() as conn:
            conn.execute('DELETE FROM master_stats WHERE timestamp < ?', (cutoff_time,))
            conn.execute('DELETE FROM lichess_stats WHERE timestamp < ?', (cutoff_time,))
            conn.commit()
            logger.info("Cleared expired cache entries")
    
    def clear_all(self):
        with self._get_connection() as conn:
            conn.execute('DELETE FROM master_stats')
            conn.execute('DELETE FROM lichess_stats')
            conn.commit()
            logger.info("Cleared all cache entries")
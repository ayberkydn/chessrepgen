import sqlite3
import json
import logging
from typing import Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class ChessCache:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS master_stats (
                    fen TEXT PRIMARY KEY,
                    data TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS lichess_stats (
                    fen TEXT,
                    rating_range TEXT,
                    time_control TEXT,
                    data TEXT,
                    PRIMARY KEY (fen, rating_range, time_control)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS stockfish_evals (
                    fen TEXT,
                    candidate_moves TEXT,
                    depth INTEGER,
                    threshold REAL,
                    acceptable_moves TEXT,
                    PRIMARY KEY (fen, candidate_moves)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS stockfish_position_evals (
                    fen TEXT,
                    depth INTEGER,
                    score REAL,
                    PRIMARY KEY (fen, depth)
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_master_fen ON master_stats(fen)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lichess_fen ON lichess_stats(fen)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stockfish_fen ON stockfish_evals(fen)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_stockfish_pos_fen ON stockfish_position_evals(fen)"
            )
            conn.commit()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_master_stats(self, fen: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT data FROM master_stats WHERE fen = ?", (fen,))
            row = cursor.fetchone()

            if row:
                data = row[0]
                logger.debug(f"Cache hit for master stats: {fen}")
                return json.loads(data)

            return None

    def set_master_stats(self, fen: str, data: dict):
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO master_stats (fen, data)
                   VALUES (?, ?)""",
                (fen, json.dumps(data)),
            )
            conn.commit()
            logger.debug(f"Cached master stats for: {fen}")

    def get_lichess_stats(
        self, fen: str, min_rating: int, max_rating: int, time_controls: list[str]
    ) -> dict | None:
        rating_range = f"{min_rating}-{max_rating}"
        time_control_str = ",".join(sorted(time_controls))

        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT data FROM lichess_stats
                   WHERE fen = ? AND rating_range = ? AND time_control = ?""",
                (fen, rating_range, time_control_str),
            )
            row = cursor.fetchone()

            if row:
                data = row[0]
                logger.debug(f"Cache hit for lichess stats: {fen}")
                return json.loads(data)

            return None

    def set_lichess_stats(
        self,
        fen: str,
        data: dict,
        min_rating: int,
        max_rating: int,
        time_controls: list[str],
    ):
        rating_range = f"{min_rating}-{max_rating}"
        time_control_str = ",".join(sorted(time_controls))

        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO lichess_stats
                   (fen, rating_range, time_control, data)
                   VALUES (?, ?, ?, ?)""",
                (fen, rating_range, time_control_str, json.dumps(data)),
            )
            conn.commit()
            logger.debug(f"Cached lichess stats for: {fen}")

    def get_stockfish_eval(
        self,
        fen: str,
        candidate_moves: list[str],
        required_depth: int,
        required_threshold: float,
    ) -> list[str] | None:
        candidate_moves_str = ",".join(sorted(candidate_moves))

        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT acceptable_moves, depth, threshold FROM stockfish_evals
                   WHERE fen = ? AND candidate_moves = ?""",
                (fen, candidate_moves_str),
            )
            row = cursor.fetchone()

            if row:
                acceptable_moves_str, cached_depth, cached_threshold = row
                # Only use cached result if depth is sufficient and threshold is compatible
                if (
                    cached_depth >= required_depth
                    and cached_threshold <= required_threshold
                ):
                    logger.debug(f"Cache hit for Stockfish eval: {fen}")
                    return (
                        acceptable_moves_str.split(",") if acceptable_moves_str else []
                    )

            return None

    def set_stockfish_eval(
        self,
        fen: str,
        candidate_moves: list[str],
        depth: int,
        threshold: float,
        acceptable_moves: list[str],
    ):
        candidate_moves_str = ",".join(sorted(candidate_moves))
        acceptable_moves_str = ",".join(acceptable_moves)

        with self._get_connection() as conn:
            # Check if we already have a deeper evaluation for these moves
            cursor = conn.execute(
                """SELECT depth FROM stockfish_evals
                   WHERE fen = ? AND candidate_moves = ?""",
                (fen, candidate_moves_str),
            )
            existing = cursor.fetchone()

            # Only update if new evaluation is deeper or doesn't exist
            if not existing or existing[0] < depth:
                conn.execute(
                    """INSERT OR REPLACE INTO stockfish_evals
                       (fen, candidate_moves, depth, threshold, acceptable_moves)
                       VALUES (?, ?, ?, ?, ?)""",
                    (fen, candidate_moves_str, depth, threshold, acceptable_moves_str),
                )
                conn.commit()
                logger.debug(f"Cached Stockfish eval for: {fen} at depth {depth}")
            else:
                logger.debug(
                    f"Skipped caching: already have depth {existing[0]} for {fen}"
                )

    def get_stockfish_position_eval(
        self, fen: str, required_depth: int
    ) -> float | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT score, depth FROM stockfish_position_evals
                   WHERE fen = ? AND depth >= ?
                   ORDER BY depth DESC
                   LIMIT 1""",
                (fen, required_depth),
            )
            row = cursor.fetchone()

            if row:
                score, cached_depth = row
                logger.debug(
                    f"Cache hit for Stockfish position eval: {fen} (depth {cached_depth})"
                )
                return score

            return None

    def set_stockfish_position_eval(self, fen: str, depth: int, score: float):
        with self._get_connection() as conn:
            # Check if we already have a deeper or equal evaluation
            cursor = conn.execute(
                """SELECT depth FROM stockfish_position_evals
                   WHERE fen = ? AND depth >= ?
                   LIMIT 1""",
                (fen, depth),
            )
            existing = cursor.fetchone()

            # Only insert/update if we don't have a deeper evaluation already
            if not existing:
                conn.execute(
                    """INSERT OR REPLACE INTO stockfish_position_evals
                       (fen, depth, score)
                       VALUES (?, ?, ?)""",
                    (fen, depth, score),
                )
                conn.commit()
                logger.debug(
                    f"Cached Stockfish position eval for: {fen} at depth {depth}"
                )
            else:
                logger.debug(
                    f"Skipped caching: already have depth {existing[0]} for {fen}"
                )

    def get_cache_stats(self) -> dict[str, int]:
        """Get statistics about cached data"""
        with self._get_connection() as conn:
            stats = {}

            cursor = conn.execute("SELECT COUNT(*) FROM master_stats")
            stats["master_positions"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM lichess_stats")
            stats["lichess_positions"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM stockfish_evals")
            stats["stockfish_move_evals"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM stockfish_position_evals")
            stats["stockfish_position_evals"] = cursor.fetchone()[0]

            # Get average depth of Stockfish evaluations
            cursor = conn.execute("SELECT AVG(depth) FROM stockfish_position_evals")
            avg_depth = cursor.fetchone()[0]
            stats["avg_stockfish_depth"] = round(avg_depth, 1) if avg_depth else 0

            return stats

    def clear_all(self):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM master_stats")
            conn.execute("DELETE FROM lichess_stats")
            conn.execute("DELETE FROM stockfish_evals")
            conn.execute("DELETE FROM stockfish_position_evals")
            conn.commit()
            logger.info("Cleared all cache entries")

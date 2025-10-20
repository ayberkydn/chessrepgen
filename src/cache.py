from __future__ import annotations

import sqlite3
import json
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

MASTER_RATING_KEY = "__master__"
MASTER_TIME_CONTROL_KEY = "__master__"


class ChessCache:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lichess_stats (
                    fen TEXT,
                    rating_range TEXT,
                    time_control TEXT,
                    data TEXT,
                    PRIMARY KEY (fen, rating_range, time_control)
                )
            """)

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lichess_fen ON lichess_stats(fen)"
            )
            conn.commit()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_lichess_stats(
        self, fen: str, ratings: list[int], time_controls: list[str]
    ) -> dict | None:
        rating_key = ",".join(map(str, sorted(ratings)))
        time_control_str = ",".join(sorted(time_controls))

        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT data FROM lichess_stats
                   WHERE fen = ? AND rating_range = ? AND time_control = ?""",
                (fen, rating_key, time_control_str),
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
        ratings: list[int],
        time_controls: list[str],
    ):
        rating_key = ",".join(map(str, sorted(ratings)))
        time_control_str = ",".join(sorted(time_controls))

        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO lichess_stats
                   (fen, rating_range, time_control, data)
                   VALUES (?, ?, ?, ?)""",
                (fen, rating_key, time_control_str, json.dumps(data)),
            )
            conn.commit()
            logger.debug(f"Cached lichess stats for: {fen}")

    def get_master_stats(self, fen: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """SELECT data FROM lichess_stats
                   WHERE fen = ? AND rating_range = ? AND time_control = ?""",
                (fen, MASTER_RATING_KEY, MASTER_TIME_CONTROL_KEY),
            )
            row = cursor.fetchone()

            if row:
                data = row[0]
                logger.debug(f"Cache hit for master stats: {fen}")
                return json.loads(data)

            return None

    def set_master_stats(self, fen: str, data: dict) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO lichess_stats
                   (fen, rating_range, time_control, data)
                   VALUES (?, ?, ?, ?)""",
                (fen, MASTER_RATING_KEY, MASTER_TIME_CONTROL_KEY, json.dumps(data)),
            )
            conn.commit()
            logger.debug(f"Cached master stats for: {fen}")

    def get_cache_stats(self) -> dict[str, int]:
        """Get statistics about cached data"""
        with self._get_connection() as conn:
            stats = {}

            cursor = conn.execute("SELECT COUNT(*) FROM lichess_stats")
            stats["lichess_positions"] = cursor.fetchone()[0]

            return stats

    def clear_all(self):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM lichess_stats")
            conn.commit()
            logger.info("Cleared all cache entries")

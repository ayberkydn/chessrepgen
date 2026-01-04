from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def normalize_fen(fen: str) -> str:
    """Normalize FEN to a stable cache key by stripping move counters."""
    parts = fen.split()
    if len(parts) <= 4:
        return fen
    return " ".join(parts[:4])


class ChessCache:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
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
        """Get a persistent connection for the current thread."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        yield self._local.conn

    def get_lichess_stats(
        self, fen: str, ratings: list[int], time_controls: list[str]
    ) -> dict | None:
        rating_key = ",".join(map(str, sorted(ratings)))
        time_control_str = ",".join(sorted(time_controls))
        normalized_fen = normalize_fen(fen)
        candidates = [normalized_fen, fen] if normalized_fen != fen else [fen]

        with self._get_connection() as conn:
            for candidate_fen in candidates:
                cursor = conn.execute(
                    """SELECT data FROM lichess_stats
                       WHERE fen = ? AND rating_range = ? AND time_control = ?""",
                    (candidate_fen, rating_key, time_control_str),
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
        normalized_fen = normalize_fen(fen)

        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO lichess_stats
                   (fen, rating_range, time_control, data)
                   VALUES (?, ?, ?, ?)""",
                (normalized_fen, rating_key, time_control_str, json.dumps(data)),
            )
            conn.commit()
            logger.debug(f"Cached lichess stats for: {fen}")


class StockfishCache:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stockfish_evaluations (
                    fen TEXT PRIMARY KEY,
                    depth INTEGER NOT NULL,
                    white_score REAL NOT NULL
                )
                """
            )
            conn.commit()

    @contextmanager
    def _get_connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        yield self._local.conn

    def get_stockfish_evaluation(self, fen: str) -> dict | None:
        normalized_fen = normalize_fen(fen)
        candidates = [normalized_fen, fen] if normalized_fen != fen else [fen]

        with self._get_connection() as conn:
            for candidate_fen in candidates:
                cursor = conn.execute(
                    """SELECT white_score, depth FROM stockfish_evaluations
                           WHERE fen = ?""",
                    (candidate_fen,),
                )
                row = cursor.fetchone()

                if row:
                    white_score, depth = row
                    logger.debug(
                        "Cache hit for Stockfish eval: %s (depth=%d)",
                        fen,
                        depth,
                    )
                    return {"white_score": white_score, "depth": depth}

            return None

    def set_stockfish_evaluation(
        self, fen: str, depth: int, white_score: float
    ) -> None:
        normalized_fen = normalize_fen(fen)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO stockfish_evaluations (fen, depth, white_score)
                VALUES (?, ?, ?)
                ON CONFLICT(fen) DO UPDATE SET
                    depth=excluded.depth,
                    white_score=excluded.white_score
                WHERE excluded.depth > stockfish_evaluations.depth
                """,
                (normalized_fen, depth, white_score),
            )
            conn.commit()
            logger.debug(
                "Cached Stockfish eval for: %s (depth=%d)",
                fen,
                depth,
            )

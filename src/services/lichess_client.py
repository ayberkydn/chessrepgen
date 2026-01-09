from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

_ = load_dotenv()

logger = logging.getLogger(__name__)


class LichessClient:
    BASE_URL = "https://explorer.lichess.ovh"

    def __init__(self):
        self.api_key = os.getenv("LICHESS_API_KEY")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
            logger.info("Lichess API key found and loaded")
        else:
            logger.warning(
                "No Lichess API key found. Using anonymous access (stricter rate limits apply)."
            )
            logger.warning(
                "To get better rate limits, create a .env file with LICHESS_API_KEY=your_key"
            )
            logger.warning(
                "Get your API key from: https://lichess.org/account/oauth/token"
            )
        self.session.headers.update({"Accept": "application/json"})
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 1 second between requests

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any],
        request_context: str | None = None,
    ) -> dict | None:
        self._rate_limit()

        url = f"{self.BASE_URL}/{endpoint}"
        context_msg = f" [{request_context}]" if request_context else ""
        logger.info("Lichess request%s: GET %s params=%s", context_msg, url, params)
        start_time = time.perf_counter()

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            elapsed = time.perf_counter() - start_time
            logger.info(
                "Lichess response%s: %s %s in %.2fs",
                context_msg,
                endpoint,
                response.status_code,
                elapsed,
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f"Error fetching data from Lichess: {e}")
            logger.info(
                "Lichess request%s %s failed with %s after %.2fs",
                context_msg,
                endpoint,
                getattr(e.response, "status_code", "no-status"),
                elapsed,
            )
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds.")
                    time.sleep(retry_after)
                    return self._make_request(
                        endpoint, params, request_context=request_context
                    )
            return None
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f"Unexpected error: {e}")
            logger.debug(
                "Lichess request %s raised unexpected error after %.2fs",
                endpoint,
                elapsed,
            )
            return None

    @staticmethod
    def _validate_position_response(data: dict | None) -> dict | None:
        """Validate that API response has expected structure.

        Returns the data if valid, None if invalid or empty.
        """
        if data is None:
            return None

        # Check for required keys in position response
        if not isinstance(data, dict):
            logger.warning("API response is not a dictionary")
            return None

        # Ensure numeric fields are present (default to 0 if missing)
        for key in ("white", "draws", "black"):
            if key not in data:
                data[key] = 0
            elif not isinstance(data[key], (int, float)):
                logger.warning(f"API response has invalid {key} field: {data[key]}")
                data[key] = 0

        # Ensure moves is a list
        if "moves" not in data:
            data["moves"] = []
        elif not isinstance(data["moves"], list):
            logger.warning(
                f"API response has invalid moves field: {type(data['moves'])}"
            )
            data["moves"] = []

        return data

    def get_lichess_games(
        self,
        fen: str,
        ratings: list[int],
        speeds: list[str],
        moves: int = 12,
        request_context: str | None = None,
    ) -> dict | None:
        params = {
            "fen": fen,
            "moves": moves,
            "ratings": ",".join(map(str, ratings)),
            "speeds": ",".join(speeds),
        }

        if self.api_key:
            params["topGames"] = 0
            params["recentGames"] = 0

        result = self._make_request("lichess", params, request_context=request_context)
        return self._validate_position_response(result)

    def get_position_stats(
        self,
        fen: str,
        ratings: list[int],
        time_controls: list[str],
        request_context: str | None = None,
    ) -> dict[str, dict | None]:
        lichess_data = self.get_lichess_games(
            fen,
            ratings,
            time_controls,
            request_context=request_context,
        )

        return {"lichess": lichess_data}

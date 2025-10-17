import os
import time
import logging
from typing import Any
import requests
from dotenv import load_dotenv
import random

_ = load_dotenv()

logger = logging.getLogger(__name__)


class LichessClient:
    BASE_URL = "https://explorer.lichess.ovh"

    def __init__(self, proxies: list[str] | None = None):
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
        self.min_request_interval = 1.0  # Increased to 1 second between requests
        self.proxies = proxies

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: dict[str, Any]) -> dict | None:
        self._rate_limit()

        url = f"{self.BASE_URL}/{endpoint}"
        logger.debug("Lichess request: GET %s params=%s", url, params)
        start_time = time.perf_counter()

        proxies = {}
        if self.proxies:
            proxy_url = random.choice(self.proxies)
            proxies = {
                "http": proxy_url,
                "https": proxy_url,
            }

        try:
            response = self.session.get(url, params=params, timeout=10, proxies=proxies)
            response.raise_for_status()
            elapsed = time.perf_counter() - start_time
            logger.debug(
                "Lichess response: %s %s in %.2fs",
                endpoint,
                response.status_code,
                elapsed,
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f"Error fetching data from Lichess: {e}")
            logger.debug("Lichess request %s failed after %.2fs", endpoint, elapsed)
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds.")
                    time.sleep(retry_after)
                    return self._make_request(endpoint, params)
            return None
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f"Unexpected error: {e}")
            logger.debug("Lichess request %s raised unexpected error after %.2fs", endpoint, elapsed)
            return None

    def get_master_games(self, fen: str, moves: int = 12) -> dict | None:
        params = {"fen": fen, "moves": moves}
        return self._make_request("masters", params)

    def get_lichess_games(
        self, fen: str, ratings: list[int], speeds: list[str], moves: int = 12
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

        return self._make_request("lichess", params)

    def get_position_stats(
        self, fen: str, min_rating: int, max_rating: int, time_controls: list[str]
    ) -> dict[str, dict | None]:
        rating_ranges = []
        current = min_rating
        while current < max_rating:
            rating_ranges.append(current)
            current += 200
        if rating_ranges[-1] != max_rating:
            rating_ranges.append(max_rating)

        master_data = self.get_master_games(fen)

        lichess_data = self.get_lichess_games(fen, rating_ranges, time_controls)

        return {"master": master_data, "lichess": lichess_data}

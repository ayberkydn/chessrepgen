from __future__ import annotations

import os
import time
import logging
from typing import Any
import requests
from dotenv import load_dotenv


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
        self._current_proxy_index = 0  # Track current proxy for round-robin selection
        self._proxy_rate_limits = {}  # Track rate limits per proxy

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _get_next_proxy(self) -> str:
        """Get the next proxy in round-robin order, skipping rate-limited proxies."""
        if not self.proxies:
            raise ValueError("No proxies available")

        # Check if current proxy is rate limited
        current_proxy = self.proxies[self._current_proxy_index]
        if self._is_proxy_rate_limited(current_proxy):
            logger.warning(f"Skipping rate-limited proxy: {current_proxy}")
            # Move to next proxy and check again
            self._current_proxy_index = (self._current_proxy_index + 1) % len(
                self.proxies
            )
            return self._get_next_proxy()  # Recursively find next available proxy

        proxy = current_proxy
        self._current_proxy_index = (self._current_proxy_index + 1) % len(self.proxies)
        return proxy

    def _is_proxy_rate_limited(self, proxy: str) -> bool:
        """Check if a proxy is currently rate limited."""
        if proxy not in self._proxy_rate_limits:
            return False

        rate_limit_until = self._proxy_rate_limits[proxy]
        return time.time() < rate_limit_until

    def _mark_proxy_rate_limited(self, proxy: str, retry_after: int) -> None:
        """Mark a proxy as rate limited until a specific time."""
        rate_limit_until = time.time() + retry_after
        self._proxy_rate_limits[proxy] = rate_limit_until
        logger.warning(
            f"Proxy {proxy} rate limited for {retry_after} seconds (until {time.ctime(rate_limit_until)})"
        )

    def _get_available_proxy_count(self) -> int:
        """Get count of proxies that are not currently rate limited."""
        if not self.proxies:
            return 0
        return sum(
            1 for proxy in self.proxies if not self._is_proxy_rate_limited(proxy)
        )

    def _cleanup_expired_rate_limits(self) -> None:
        """Remove expired rate limit entries."""
        current_time = time.time()
        expired_proxies = [
            proxy
            for proxy, rate_limit_until in self._proxy_rate_limits.items()
            if current_time >= rate_limit_until
        ]

        for proxy in expired_proxies:
            del self._proxy_rate_limits[proxy]
            logger.info(f"Proxy {proxy} rate limit expired, now available")

    def get_proxy_status(self) -> dict[str, dict]:
        """Get current status of all proxies."""
        if not self.proxies:
            return {}

        status = {}
        current_time = time.time()

        for proxy in self.proxies:
            if proxy in self._proxy_rate_limits:
                rate_limit_until = self._proxy_rate_limits[proxy]
                if current_time < rate_limit_until:
                    remaining = int(rate_limit_until - current_time)
                    status[proxy] = {
                        "status": "rate_limited",
                        "available_in": remaining,
                        "available_at": time.ctime(rate_limit_until),
                    }
                else:
                    status[proxy] = {"status": "available"}
            else:
                status[proxy] = {"status": "available"}

        return status

    def _make_request(self, endpoint: str, params: dict[str, Any]) -> dict | None:
        self._rate_limit()
        self._cleanup_expired_rate_limits()  # Clean up expired rate limits

        url = f"{self.BASE_URL}/{endpoint}"
        logger.debug("Lichess request: GET %s params=%s", url, params)
        start_time = time.perf_counter()

        proxies = {}
        if self.proxies:
            try:
                proxy_url = self._get_next_proxy()
                proxies = {
                    "http": proxy_url,
                    "https": proxy_url,
                }
            except ValueError as e:
                # All proxies are rate limited
                logger.error("No available proxies - all are rate limited")
                return None

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

                    if proxies:
                        # Using proxy - mark it as rate limited and try next proxy
                        self._mark_proxy_rate_limited(proxy_url, retry_after)
                        available_proxies = self._get_available_proxy_count()

                        if available_proxies > 0:
                            logger.info(
                                f"Rate limited on proxy {proxy_url}, trying another proxy "
                                f"({available_proxies} proxies still available)"
                            )
                            return self._make_request(endpoint, params)
                        else:
                            logger.warning(
                                f"All proxies are rate limited. Waiting {retry_after} seconds."
                            )
                            time.sleep(retry_after)
                            return self._make_request(endpoint, params)
                    else:
                        # Not using proxy - wait as before
                        logger.warning(f"Rate limited. Waiting {retry_after} seconds.")
                        time.sleep(retry_after)
                        return self._make_request(endpoint, params)
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

    def get_master_games(self, fen: str, moves: int = 12) -> dict | None:
        params = {
            "fen": fen,
            "moves": moves,
        }

        return self._make_request("master", params)

    def get_position_stats(
        self, fen: str, ratings: list[int], time_controls: list[str]
    ) -> dict[str, dict | None]:
        lichess_data = self.get_lichess_games(fen, ratings, time_controls)

        return {"lichess": lichess_data}

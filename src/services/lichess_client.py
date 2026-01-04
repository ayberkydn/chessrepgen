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

    def _get_next_proxy(self) -> str | None:
        """Get the next proxy in round-robin order, skipping rate-limited proxies.

        Returns None if all proxies are rate-limited.
        """
        if not self.proxies:
            raise ValueError("No proxies available")

        # Track starting index to detect when we've checked all proxies
        start_index = self._current_proxy_index
        checked_count = 0

        while checked_count < len(self.proxies):
            current_proxy = self.proxies[self._current_proxy_index]
            self._current_proxy_index = (self._current_proxy_index + 1) % len(
                self.proxies
            )
            checked_count += 1

            if not self._is_proxy_rate_limited(current_proxy):
                return current_proxy

            logger.warning(f"Skipping rate-limited proxy: {current_proxy}")

        # All proxies are rate-limited
        logger.error("All proxies are currently rate-limited")
        return None

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

    def _get_shortest_rate_limit_wait(self) -> float | None:
        """Get the shortest time until any proxy becomes available."""
        if not self._proxy_rate_limits:
            return None

        current_time = time.time()
        min_wait = None

        for proxy, rate_limit_until in self._proxy_rate_limits.items():
            wait_time = rate_limit_until - current_time
            if wait_time > 0:
                if min_wait is None or wait_time < min_wait:
                    min_wait = wait_time

        return min_wait

    def _cleanup_expired_rate_limits(self) -> None:
        """Remove expired rate limit entries."""
        current_time = time.time()
        expired_proxies = [
            proxy_key
            for proxy_key, rate_limit_until in self._proxy_rate_limits.items()
            if current_time >= rate_limit_until
        ]

        for proxy_key in expired_proxies:
            del self._proxy_rate_limits[proxy_key]
            logger.info(f"Proxy {proxy_key} rate limit expired, now available")

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any],
        request_context: str | None = None,
    ) -> dict | None:
        self._rate_limit()
        self._cleanup_expired_rate_limits()  # Clean up expired rate limits

        url = f"{self.BASE_URL}/{endpoint}"
        context_msg = f" [{request_context}]" if request_context else ""
        logger.info("Lichess request%s: GET %s params=%s", context_msg, url, params)
        start_time = time.perf_counter()

        proxies = {}
        proxy_url = None
        if self.proxies:
            proxy_url = self._get_next_proxy()
            if proxy_url is None:
                # All proxies are rate limited - wait for shortest rate limit to expire
                min_wait = self._get_shortest_rate_limit_wait()
                if min_wait is not None and min_wait > 0:
                    logger.warning(
                        f"All proxies rate-limited. Waiting {min_wait:.1f}s for shortest limit to expire."
                    )
                    time.sleep(min_wait + 0.1)  # Add small buffer
                    self._cleanup_expired_rate_limits()
                    proxy_url = self._get_next_proxy()

                if proxy_url is None:
                    logger.error("No available proxies after waiting")
                    return None

            proxies = {
                "http": proxy_url,
                "https": proxy_url,
            }

        try:
            response = self.session.get(url, params=params, timeout=10, proxies=proxies)
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

                    if proxies:
                        # Using proxy - mark it as rate limited and try next proxy
                        self._mark_proxy_rate_limited(proxy_url, retry_after)
                        available_proxies = self._get_available_proxy_count()

                        if available_proxies > 0:
                            logger.info(
                                f"Rate limited on proxy {proxy_url}, trying another proxy "
                                f"({available_proxies} proxies still available)"
                            )
                            return self._make_request(
                                endpoint, params, request_context=request_context
                            )
                        else:
                            logger.warning(
                                f"All proxies are rate limited. Waiting {retry_after} seconds."
                            )
                            time.sleep(retry_after)
                            return self._make_request(
                                endpoint, params, request_context=request_context
                            )
                    else:
                        # Not using proxy - wait as before
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

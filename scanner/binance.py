"""Async client for Binance FREE public REST endpoints.

Only unauthenticated market-data endpoints are used:

Futures (USDS-M, ``fapi.binance.com``):
    - ``/fapi/v1/ticker/24hr``            24h stats for every futures symbol
    - ``/fapi/v1/premiumIndex``           mark price + last funding rate
    - ``/fapi/v1/fundingRate``            historical funding rates
    - ``/futures/data/openInterestHist``  open interest history

Spot (``api.binance.com``):
    - ``/api/v3/exchangeInfo``            list of tradable spot symbols
"""
from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import Any

import aiohttp

logger = logging.getLogger("binance")


class BinanceError(Exception):
    """Raised when a Binance request fails after all retries."""


class BinanceClient:
    """Thin async HTTP client with retries, backoff and bounded concurrency."""

    def __init__(
        self,
        futures_url: str,
        spot_url: str,
        max_concurrency: int = 8,
        max_retries: int = 4,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._futures_url = futures_url.rstrip("/")
        self._spot_url = spot_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_retries = max_retries
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "BinanceClient":
        self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------ #
    # Low-level request handling
    # ------------------------------------------------------------------ #

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET with exponential backoff. Honours HTTP 429/418 Retry-After."""
        if self._session is None:
            raise BinanceError("client session not started (use 'async with')")

        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                async with self._semaphore:
                    logger.debug("GET %s params=%s", url, params)
                    async with self._session.get(url, params=params) as resp:
                        if resp.status in (418, 429):
                            wait = float(resp.headers.get("Retry-After", delay))
                            logger.warning(
                                "Rate limited (HTTP %d) on %s; backing off %.1fs",
                                resp.status, url, wait,
                            )
                            await asyncio.sleep(wait)
                            raise aiohttp.ClientResponseError(
                                resp.request_info, resp.history,
                                status=resp.status, message="rate limited",
                            )
                        resp.raise_for_status()
                        return await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    logger.warning(
                        "GET %s failed (attempt %d/%d): %s — retrying in %.1fs",
                        url, attempt, self._max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
        raise BinanceError(
            f"GET {url} failed after {self._max_retries} attempts: {last_error}"
        )

    # ------------------------------------------------------------------ #
    # Futures endpoints
    # ------------------------------------------------------------------ #

    async def futures_24h_tickers(self) -> list[dict[str, Any]]:
        """24h rolling-window stats for every USDS-M futures symbol."""
        return await self._get(f"{self._futures_url}/fapi/v1/ticker/24hr")

    async def premium_index(self, symbol: str) -> dict[str, Any]:
        """Mark price + last funding rate for one symbol."""
        return await self._get(
            f"{self._futures_url}/fapi/v1/premiumIndex", {"symbol": symbol}
        )

    async def funding_history(
        self, symbol: str, limit: int = 48
    ) -> list[dict[str, Any]]:
        """Historical funding rate records (8h interval) for one symbol."""
        return await self._get(
            f"{self._futures_url}/fapi/v1/fundingRate",
            {"symbol": symbol, "limit": limit},
        )

    async def open_interest_hist(
        self, symbol: str, period: str = "5m", limit: int = 6
    ) -> list[dict[str, Any]]:
        """Open interest history for one symbol."""
        return await self._get(
            f"{self._futures_url}/futures/data/openInterestHist",
            {"symbol": symbol, "period": period, "limit": limit},
        )

    # ------------------------------------------------------------------ #
    # Spot endpoints
    # ------------------------------------------------------------------ #

    async def spot_symbols(self) -> set[str]:
        """Set of spot symbols currently in TRADING status."""
        data = await self._get(f"{self._spot_url}/api/v3/exchangeInfo")
        return {
            s["symbol"]
            for s in data.get("symbols", [])
            if s.get("status") == "TRADING"
        }

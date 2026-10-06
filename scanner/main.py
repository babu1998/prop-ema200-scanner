"""Binance Futures Funding Divergence Scanner — entry point.

Flow:
    hourly   -> refresh the top-10 24h gainers (the monitored set)
    6-hourly -> refresh the spot exchangeInfo symbol set
    5-min    -> snapshot funding + mark price for every monitored symbol,
                compare with the previous snapshot, and alert on divergence.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time

import aiohttp

from alerts import DiscordAlerter, build_divergence_embed
from binance import BinanceClient, BinanceError
from charting import render_funding_chart
from config import Config
from database import Database
from funding import (
    FundingSnapshot,
    detect_divergence,
    funding_quotient,
    spot_filter_passes,
)
from leaderboard import send_leaderboard
from logger import setup_logging
from metrics import Metrics
from oi_filter import oi_confirms
from ranking import top_gainers
from scheduler import build_scheduler
from telegram_alerts import TelegramAlerter, build_divergence_text
from utils import safe_float, utc_now_ms

logger = logging.getLogger("main")

# Keep at most 7 days of snapshots in the database.
SNAPSHOT_RETENTION_MS = 7 * 24 * 3600 * 1000


class Scanner:
    """Holds runtime state and implements all scheduled jobs."""

    def __init__(
        self,
        cfg: Config,
        client: BinanceClient,
        db: Database,
        discord: DiscordAlerter,
        telegram: TelegramAlerter,
        metrics: Metrics,
    ) -> None:
        self._cfg = cfg
        self._client = client
        self._db = db
        self._discord = discord
        self._telegram = telegram
        self._metrics = metrics
        self._ranks: dict[str, int] = {}   # symbol -> 24h gainers rank
        self._spot_symbols: set[str] = set()

    # ------------------------------------------------------------------ #
    # Scheduled jobs
    # ------------------------------------------------------------------ #

    async def refresh_top(self) -> None:
        """Hourly: rebuild the monitored set from the top 24h gainers."""
        try:
            tickers = await self._client.futures_24h_tickers()
        except BinanceError as exc:
            self._metrics.api_error()
            logger.error("Top gainers refresh failed (keeping old set): %s", exc)
            return

        ranked = top_gainers(tickers, self._cfg.top_coins)
        self._ranks = {r.symbol: r.rank for r in ranked}
        self._metrics.set_monitored(len(self._ranks))
        logger.info(
            "Top %d gainers refreshed: %s",
            self._cfg.top_coins,
            ", ".join(
                f"#{r.rank} {r.symbol} ({r.price_change_percent:+.2f}%)"
                for r in ranked
            ),
        )

    async def refresh_spot(self) -> None:
        """Every 6 h: refresh the set of tradable spot symbols."""
        try:
            self._spot_symbols = await self._client.spot_symbols()
            logger.info(
                "Spot exchangeInfo refreshed: %d tradable symbols",
                len(self._spot_symbols),
            )
        except BinanceError as exc:
            self._metrics.api_error()
            logger.error("Spot refresh failed (keeping old set): %s", exc)

    async def scan(self) -> None:
        """Every 5 min: snapshot all monitored symbols and check divergences."""
        started = time.monotonic()
        if not self._ranks:
            await self.refresh_top()
            if not self._ranks:
                logger.warning("No monitored symbols — skipping scan")
                return

        results = await asyncio.gather(
            *(
                self._scan_symbol(symbol, rank)
                for symbol, rank in self._ranks.items()
            ),
            return_exceptions=True,
        )
        for symbol, result in zip(self._ranks, results):
            if isinstance(result, BaseException):
                logger.error("Scan failed for %s: %s", symbol, result)

        self._db.prune_snapshots(utc_now_ms() - SNAPSHOT_RETENTION_MS)
        duration = time.monotonic() - started
        self._metrics.scan_completed(duration)
        logger.info(
            "Scan finished: %d symbols in %.2fs", len(self._ranks), duration
        )

    async def post_leaderboard(self) -> None:
        """Optional job: post the top funding movers leaderboard."""
        await send_leaderboard(
            self._db,
            self._discord,
            window_seconds=self._cfg.leaderboard_interval,
            top_n=self._cfg.leaderboard_size,
        )

    # ------------------------------------------------------------------ #
    # Per-symbol pipeline
    # ------------------------------------------------------------------ #

    async def _scan_symbol(self, symbol: str, rank: int) -> None:
        """Snapshot one symbol, then run filters and alerting."""
        try:
            data = await self._client.premium_index(symbol)
        except BinanceError as exc:
            self._metrics.api_error()
            logger.error("premiumIndex failed for %s: %s", symbol, exc)
            return

        curr = FundingSnapshot(
            symbol=symbol,
            timestamp=int(data.get("time") or utc_now_ms()),
            price=safe_float(data.get("markPrice")),
            funding=safe_float(data.get("lastFundingRate")),
        )

        prev_row = self._db.last_snapshot(symbol)
        prev: FundingSnapshot | None = None
        if prev_row is not None:
            prev = FundingSnapshot(
                symbol=symbol,
                timestamp=int(prev_row["timestamp"]),
                price=float(prev_row["price"]),
                funding=float(prev_row["funding"]),
            )

        quotient = (
            funding_quotient(prev.funding, curr.funding) if prev else None
        )
        self._db.insert_snapshot(
            symbol, curr.timestamp, curr.price, curr.funding, quotient
        )

        if prev is None:
            logger.debug("%s: first snapshot — baseline only", symbol)
            return
        # A stale previous snapshot (symbol re-entered the top list after a
        # gap) is only a new baseline, not a comparison point.
        if curr.timestamp - prev.timestamp > 2 * self._cfg.scan_interval * 1000:
            logger.debug("%s: previous snapshot stale — baseline reset", symbol)
            return

        has_spot = symbol in self._spot_symbols
        if not spot_filter_passes(curr.funding, has_spot):
            logger.debug(
                "%s: spot filter blocked (funding=%s, spot=%s)",
                symbol, curr.funding, has_spot,
            )
            return

        divergence = detect_divergence(
            prev, curr, self._cfg.price_threshold, self._cfg.funding_threshold
        )
        if divergence is None:
            return

        last_alert = self._db.last_alert_ts(symbol)
        if (
            last_alert is not None
            and curr.timestamp - last_alert < self._cfg.alert_cooldown * 1000
        ):
            logger.info("%s: divergence found but within cooldown — skipped",
                        symbol)
            return

        oi_note: str | None = None
        if self._cfg.oi_filter_enabled:
            passed, oi_note = await oi_confirms(
                self._client, symbol,
                self._cfg.oi_period, self._cfg.oi_lookback,
                self._cfg.oi_threshold,
            )
            if not passed:
                logger.info(
                    "%s: divergence rejected by OI filter (%s)", symbol, oi_note
                )
                return

        png: bytes | None = None
        if self._cfg.chart_enabled:
            try:
                history = await self._client.funding_history(
                    symbol, self._cfg.chart_points
                )
                png = render_funding_chart(symbol, history)
            except BinanceError as exc:
                self._metrics.api_error()
                logger.warning("Funding history failed for %s: %s", symbol, exc)

        embed = build_divergence_embed(
            divergence, rank, has_spot, with_chart=png is not None,
            oi_note=oi_note,
        )
        sent = await self._discord.send_embed(embed, png)
        if self._telegram.enabled:
            await self._telegram.send_text(
                build_divergence_text(divergence, rank, has_spot)
            )

        self._db.insert_alert(symbol, curr.timestamp, divergence.alert_type)
        self._metrics.alert_sent(divergence.alert_type)
        logger.info(
            "ALERT %s %s: price %+.2f%%, quotient %+.1f%% (discord=%s)",
            symbol, divergence.alert_type, divergence.price_change_pct,
            divergence.quotient * 100.0, "ok" if sent else "failed",
        )


async def run() -> None:
    """Wire everything up and run until SIGINT/SIGTERM."""
    cfg = Config.load()
    setup_logging(cfg.log_level)
    logger.info("Funding Divergence Scanner starting")
    if not cfg.discord_webhook:
        logger.warning("DISCORD_WEBHOOK is empty — alerts will be logged only")

    metrics = Metrics(cfg.metrics_enabled, cfg.metrics_port)
    db = Database(cfg.db_path)

    async with BinanceClient(
        cfg.binance_base_url, cfg.binance_spot_url, cfg.max_concurrency
    ) as client, aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as alert_session:
        scanner = Scanner(
            cfg,
            client,
            db,
            DiscordAlerter(alert_session, cfg.discord_webhook),
            TelegramAlerter(
                alert_session, cfg.telegram_bot_token, cfg.telegram_chat_id
            ),
            metrics,
        )

        # Initial state, then an immediate first scan.
        await scanner.refresh_spot()
        await scanner.refresh_top()
        await scanner.scan()

        scheduler = build_scheduler(scanner, cfg)
        scheduler.start()

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)
        try:
            await stop.wait()
        finally:
            logger.info("Shutting down")
            scheduler.shutdown(wait=False)
            db.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

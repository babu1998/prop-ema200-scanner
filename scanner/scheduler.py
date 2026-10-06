"""APScheduler job wiring.

Jobs:
    - scan             every SCAN_INTERVAL seconds (default 5 min)
    - refresh_top      every TOP_REFRESH seconds  (default 1 h)
    - refresh_spot     every SPOT_REFRESH seconds (default 6 h)
    - leaderboard      every LEADERBOARD_INTERVAL seconds (optional)

``max_instances=1`` + ``coalesce=True`` guarantee that a slow cycle is never
overlapped or queued up by the next trigger.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import Config

if TYPE_CHECKING:  # avoid a circular import at runtime
    from main import Scanner

logger = logging.getLogger("scheduler")


def build_scheduler(scanner: "Scanner", cfg: Config) -> AsyncIOScheduler:
    """Create and configure (but do not start) the job scheduler."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    job_defaults = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 60}

    scheduler.add_job(
        scanner.scan, "interval", seconds=cfg.scan_interval,
        id="scan", **job_defaults,
    )
    scheduler.add_job(
        scanner.refresh_top, "interval", seconds=cfg.top_refresh,
        id="refresh_top", **job_defaults,
    )
    scheduler.add_job(
        scanner.refresh_spot, "interval", seconds=cfg.spot_refresh,
        id="refresh_spot", **job_defaults,
    )
    if cfg.leaderboard_enabled:
        scheduler.add_job(
            scanner.post_leaderboard, "interval",
            seconds=cfg.leaderboard_interval,
            id="leaderboard", **job_defaults,
        )

    logger.info(
        "Scheduler configured: scan=%ds, top_refresh=%ds, spot_refresh=%ds,"
        " leaderboard=%s",
        cfg.scan_interval, cfg.top_refresh, cfg.spot_refresh,
        f"{cfg.leaderboard_interval}s" if cfg.leaderboard_enabled else "off",
    )
    return scheduler

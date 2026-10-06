"""Optional top funding movers leaderboard (bonus module).

Periodically posts the symbols whose funding rate changed the most (by
absolute funding quotient) over the recent window, computed from stored
snapshots.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from sqlite3 import Row

from alerts import DiscordAlerter
from database import Database
from funding import funding_quotient
from utils import fmt_funding, fmt_pct, ms_to_iso, utc_now_ms

logger = logging.getLogger("leaderboard")


@dataclass(frozen=True)
class FundingMover:
    symbol: str
    first_funding: float
    last_funding: float
    quotient: float  # fractional


def compute_movers(rows: list[Row], top_n: int) -> list[FundingMover]:
    """Rank symbols by absolute funding quotient over the snapshot window."""
    first_last: dict[str, tuple[float, float]] = {}
    for row in rows:  # rows are ordered by (symbol, timestamp)
        symbol = row["symbol"]
        funding = float(row["funding"])
        if symbol not in first_last:
            first_last[symbol] = (funding, funding)
        else:
            first_last[symbol] = (first_last[symbol][0], funding)

    movers: list[FundingMover] = []
    for symbol, (first, last) in first_last.items():
        quotient = funding_quotient(first, last)
        if quotient is None:
            continue
        movers.append(FundingMover(symbol, first, last, quotient))
    movers.sort(key=lambda m: abs(m.quotient), reverse=True)
    return movers[:top_n]


async def send_leaderboard(
    db: Database,
    alerter: DiscordAlerter,
    window_seconds: int,
    top_n: int,
) -> None:
    """Post the funding movers leaderboard to Discord."""
    now_ms = utc_now_ms()
    rows = db.snapshots_since(now_ms - window_seconds * 1000)
    movers = compute_movers(rows, top_n)
    if not movers:
        logger.info("Leaderboard: no funding movers in window — nothing to post")
        return

    lines = [
        f"**#{i}** `{m.symbol}` — {fmt_funding(m.first_funding)} → "
        f"{fmt_funding(m.last_funding)} "
        f"(quotient {fmt_pct(m.quotient * 100.0, decimals=1)})"
        for i, m in enumerate(movers, start=1)
    ]
    embed = {
        "title": "📊 Top Funding Movers",
        "description": "\n".join(lines),
        "color": 0x5865F2,
        "footer": {"text": ms_to_iso(now_ms)},
    }
    if await alerter.send_embed(embed):
        logger.info("Leaderboard posted (%d symbols)", len(movers))

"""Discord webhook alert delivery and embed building."""
from __future__ import annotations

import json
import logging

import aiohttp

from funding import PRICE_UP_FUNDING_DOWN, Divergence
from utils import fmt_funding, fmt_pct, ms_to_iso

logger = logging.getLogger("alerts")

_GREEN = 0x2ECC71
_RED = 0xE74C3C
_CHART_FILENAME = "funding_chart.png"


def build_divergence_embed(
    divergence: Divergence,
    rank: int,
    has_spot_market: bool,
    with_chart: bool = False,
    oi_note: str | None = None,
) -> dict:
    """Build the Discord embed payload for a divergence alert."""
    fields = [
        {"name": "Coin", "value": divergence.symbol, "inline": True},
        {"name": "24h Rank", "value": f"#{rank}", "inline": True},
        {
            "name": "Price",
            "value": (
                f"{divergence.prev_price:g} → {divergence.curr_price:g}\n"
                f"{fmt_pct(divergence.price_change_pct)}"
            ),
            "inline": True,
        },
        {
            "name": "Funding",
            "value": (
                f"{fmt_funding(divergence.prev_funding)} → "
                f"{fmt_funding(divergence.curr_funding)}"
            ),
            "inline": True,
        },
        {
            "name": "Funding Quotient",
            "value": fmt_pct(divergence.quotient * 100.0, decimals=1),
            "inline": True,
        },
        {
            "name": "Spot Available",
            "value": "Yes" if has_spot_market else "No",
            "inline": True,
        },
        {"name": "Signal", "value": divergence.signal, "inline": False},
    ]
    if oi_note:
        fields.append({"name": "Open Interest", "value": oi_note, "inline": False})

    embed: dict = {
        "title": "🚨 Funding Divergence",
        "color": _GREEN if divergence.alert_type == PRICE_UP_FUNDING_DOWN else _RED,
        "fields": fields,
        "footer": {"text": ms_to_iso(divergence.timestamp)},
    }
    if with_chart:
        embed["image"] = {"url": f"attachment://{_CHART_FILENAME}"}
    return embed


class DiscordAlerter:
    """Sends embeds (optionally with a PNG attachment) to a Discord webhook."""

    def __init__(self, session: aiohttp.ClientSession, webhook_url: str) -> None:
        self._session = session
        self._webhook_url = webhook_url

    @property
    def enabled(self) -> bool:
        return bool(self._webhook_url)

    async def send_embed(self, embed: dict, png: bytes | None = None) -> bool:
        """Deliver one embed; returns True on success."""
        if not self.enabled:
            logger.warning("DISCORD_WEBHOOK not configured — alert skipped")
            return False

        payload = {"embeds": [embed]}
        try:
            if png is None:
                async with self._session.post(
                    self._webhook_url, json=payload
                ) as resp:
                    body = await resp.text()
            else:
                form = aiohttp.FormData()
                form.add_field("payload_json", json.dumps(payload))
                form.add_field(
                    "files[0]",
                    png,
                    filename=_CHART_FILENAME,
                    content_type="image/png",
                )
                async with self._session.post(
                    self._webhook_url, data=form
                ) as resp:
                    body = await resp.text()
            if resp.status >= 400:
                logger.error("Discord webhook HTTP %d: %s", resp.status, body[:300])
                return False
            return True
        except aiohttp.ClientError as exc:
            logger.error("Discord webhook request failed: %s", exc)
            return False

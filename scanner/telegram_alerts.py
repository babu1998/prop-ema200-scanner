"""Optional Telegram alert delivery (bonus module).

Enabled by setting TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the .env file.
"""
from __future__ import annotations

import logging

import aiohttp

from funding import Divergence
from utils import fmt_funding, fmt_pct, ms_to_iso

logger = logging.getLogger("telegram")


def build_divergence_text(
    divergence: Divergence, rank: int, has_spot_market: bool
) -> str:
    """Plain-text version of the divergence alert for Telegram."""
    return (
        "🚨 Funding Divergence\n"
        f"Coin: {divergence.symbol} (24h rank #{rank})\n"
        f"Price: {divergence.prev_price:g} → {divergence.curr_price:g} "
        f"({fmt_pct(divergence.price_change_pct)})\n"
        f"Funding: {fmt_funding(divergence.prev_funding)} → "
        f"{fmt_funding(divergence.curr_funding)}\n"
        f"Funding Quotient: {fmt_pct(divergence.quotient * 100.0, decimals=1)}\n"
        f"Spot Available: {'Yes' if has_spot_market else 'No'}\n"
        f"Signal: {divergence.signal}\n"
        f"{ms_to_iso(divergence.timestamp)}"
    )


class TelegramAlerter:
    """Sends messages through the Telegram Bot API."""

    def __init__(
        self, session: aiohttp.ClientSession, bot_token: str, chat_id: str
    ) -> None:
        self._session = session
        self._bot_token = bot_token
        self._chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    async def send_text(self, text: str) -> bool:
        """Send one plain-text message; returns True on success."""
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            async with self._session.post(
                url, json={"chat_id": self._chat_id, "text": text}
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.error("Telegram HTTP %d: %s", resp.status, body[:300])
                    return False
                return True
        except aiohttp.ClientError as exc:
            logger.error("Telegram request failed: %s", exc)
            return False

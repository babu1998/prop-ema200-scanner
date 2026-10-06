"""
Discord reporter — sends webhook messages and chart PNGs.

Message layout (each chunk ≤ 2000 chars):
  1. Header banner + timestamp
  2. Top Longs block
  3. Top Shorts block
  4. Footer / disclaimer
"""

import requests
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.setup_generator import TradeSetup


MAX_MSG = 1980   # leave safety margin below Discord's 2000


# ── formatting helpers ─────────────────────────────────────────────────────────

def _fp(v: float) -> str:
    """Format price intelligently."""
    if v >= 10_000: return f"{v:,.1f}"
    if v >= 1_000:  return f"{v:,.2f}"
    if v >= 10:     return f"{v:,.3f}"
    if v >= 1:      return f"{v:,.4f}"
    if v >= 0.01:   return f"{v:,.5f}"
    return f"{v:,.8f}"


def _setup_block(setup: TradeSetup, rank: int) -> str:
    d  = setup.direction
    em = "🟢" if d == "LONG" else "🔴"
    sc = setup.score

    body = (
        f"**#{rank}  {setup.symbol}**  {em} `{d}`\n"
        f"```\n"
        f"Score        {sc.total:>5.0f} / 100   {sc.conviction}\n"
        f"Probability  {setup.probability:>5.0f}%\n"
        f"\n"
        f"Entry Zone   {_fp(setup.entry_low)} — {_fp(setup.entry_high)}\n"
        f"Stop Loss    {_fp(setup.stop_loss)}\n"
        f"TP1          {_fp(setup.tp1)}\n"
        f"TP2          {_fp(setup.tp2)}\n"
        f"TP3          {_fp(setup.tp3)}\n"
        f"Invalidation {_fp(setup.invalidation)}\n"
        f"Risk/Reward  1:{setup.risk_reward:.1f}\n"
        f"```\n"
    )

    if setup.reasoning:
        body += "**Analysis:**\n"
        for line in setup.reasoning[:5]:
            body += f"> {line}\n"
    body += "\n"
    return body


def _split(text: str) -> List[str]:
    """Split text into ≤ MAX_MSG chunks on newline boundaries."""
    if len(text) <= MAX_MSG:
        return [text]
    chunks, buf = [], ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > MAX_MSG:
            chunks.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        chunks.append(buf)
    return chunks


# ── public API ────────────────────────────────────────────────────────────────

def build_messages(
    top_longs:  List[TradeSetup],
    top_shorts: List[TradeSetup],
    timestamp:  datetime,
) -> List[str]:
    ts = timestamp.strftime("%Y-%m-%d  %H:%M  UTC")

    header = (
        "```\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  BREAKOUT PROP  ✦  EMA200 MARKET STRUCTURE BOT\n"
        "  Binance USDT Perpetual Futures\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "```\n"
        f"**Analysis:** `{ts}`\n"
        f"**Strategy:** EMA200 · Market Structure · Volume · R:R ≥ 1:{int(2)}\n"
        f"**Timeframes:** 1H → 4H → Daily (short-term focus)\n"
        f"**Scoring:** 4H EMA(30) · 1H EMA(15) · Daily EMA(15) · Structure(20) · "
        f"Volume(10) · OI(5) · S/R(5)\n"
    )

    longs_section = "## 🟢  TOP LONG SETUPS\n"
    if top_longs:
        for i, s in enumerate(top_longs, 1):
            longs_section += _setup_block(s, i)
    else:
        longs_section += "*No qualifying long setups at this 1H close.*\n"

    shorts_section = "## 🔴  TOP SHORT SETUPS\n"
    if top_shorts:
        for i, s in enumerate(top_shorts, 1):
            shorts_section += _setup_block(s, i)
    else:
        shorts_section += "*No qualifying short setups at this 1H close.*\n"

    footer = (
        "```\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  Algorithmic analysis only — not financial advice.\n"
        "  Always use proper position sizing & risk management.\n"
        f"  Next report: ~1 hour  ·  Breakout Prop EMA200 Bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "```"
    )

    messages: List[str] = []
    for block in [header, longs_section, shorts_section, footer]:
        messages.extend(_split(block))
    return messages


def send_to_discord(
    webhook_url: str,
    top_longs:   List[TradeSetup],
    top_shorts:  List[TradeSetup],
    timestamp:   datetime,
    chart_paths: Optional[List[str]] = None,
) -> bool:
    if not webhook_url:
        print("  [Discord] No webhook URL configured — skipping send.")
        return False

    messages = build_messages(top_longs, top_shorts, timestamp)
    ok = True

    for msg in messages:
        try:
            r = requests.post(webhook_url, json={"content": msg}, timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  [Discord] message send failed: {e}")
            ok = False

    if chart_paths:
        for path in chart_paths:
            p = Path(path)
            if not p.exists():
                continue
            try:
                with open(p, "rb") as f:
                    r = requests.post(
                        webhook_url,
                        files={"file": (p.name, f, "image/png")},
                        timeout=30,
                    )
                    r.raise_for_status()
            except Exception as e:
                print(f"  [Discord] chart upload failed ({p.name}): {e}")
                ok = False

    return ok

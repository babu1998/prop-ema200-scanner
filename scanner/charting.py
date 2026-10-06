"""Optional funding history chart rendering (bonus module).

Renders a PNG of the recent funding-rate history so it can be attached to
the Discord alert.  Requires matplotlib; if it is not installed the module
degrades gracefully and alerts are sent without a chart.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("charting")

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on environment
    MATPLOTLIB_AVAILABLE = False


def render_funding_chart(
    symbol: str, history: list[dict[str, Any]]
) -> bytes | None:
    """Render funding history to PNG bytes; None if unavailable/empty."""
    if not MATPLOTLIB_AVAILABLE:
        logger.debug("matplotlib not installed — skipping chart")
        return None
    if len(history) < 2:
        return None

    times = [
        datetime.fromtimestamp(int(row["fundingTime"]) / 1000, tz=timezone.utc)
        for row in history
    ]
    rates = [float(row["fundingRate"]) * 100.0 for row in history]

    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=110)
    try:
        ax.plot(times, rates, color="#4c9be8", linewidth=1.6, marker="o",
                markersize=2.5)
        ax.axhline(0.0, color="#888888", linewidth=0.8, linestyle="--")
        ax.set_title(f"{symbol} funding rate history")
        ax.set_ylabel("Funding rate (%)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        ax.grid(alpha=0.25)
        fig.autofmt_xdate()
        fig.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
        return buffer.getvalue()
    except Exception as exc:  # noqa: BLE001 - chart must never break alerting
        logger.error("Chart rendering failed for %s: %s", symbol, exc)
        return None
    finally:
        plt.close(fig)

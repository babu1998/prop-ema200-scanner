"""
PNG chart generator.

Dark TradingView-style chart with:
  • Candlesticks
  • EMA200 (orange)
  • Support (green dashed)
  • Resistance (red dashed)
  • Entry zone (blue dashed)
  • Stop loss (red solid)
  • TP1/TP2/TP3 (green shades)
"""

import io
from pathlib import Path
from typing import Optional

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D
import mplfinance as mpf

import config
from src.ema_analysis     import EMAResult, calculate_ema
from src.sr_analysis      import SRResult
from src.setup_generator  import TradeSetup


# ── colours ────────────────────────────────────────────────────────────────────

BG        = "#131722"
PANEL_BG  = "#1E222D"
GRID      = "#2a2e39"
TEXT      = "#D1D4DC"
UP        = "#26A69A"
DOWN      = "#EF5350"

EMA_C     = "#FF8C00"
SUP_C     = "#26A69A"
RES_C     = "#EF5350"
ENTRY_C   = "#5C9BD6"
SL_C      = "#EF5350"
TP1_C     = "#66BB6A"
TP2_C     = "#43A047"
TP3_C     = "#2E7D32"


def _fmt_price(v: float) -> str:
    if v >= 1000: return f"{v:,.2f}"
    if v >= 1:    return f"{v:,.4f}"
    return f"{v:,.6f}"


def generate_chart(
    symbol:   str,
    df_4h:    pd.DataFrame,
    h4_ema:   EMAResult,
    sr:       SRResult,
    setup:    Optional[TradeSetup] = None,
) -> Optional[str]:
    """Render chart and return the saved PNG path, or None on failure."""

    config.CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = config.CHARTS_DIR / f"{symbol}_4h.png"

    n  = config.CHART_CANDLES
    df = df_4h.tail(n).copy()

    # Recalculate EMA200 on full series then trim to view window
    ema_full  = calculate_ema(df_4h["close"], 200)
    ema_view  = ema_full.tail(n).reindex(df.index)

    # ── mpf style ─────────────────────────────────────────────────────────────
    mc = mpf.make_marketcolors(
        up=UP, down=DOWN,
        wick={"up": UP, "down": DOWN},
        edge={"up": UP, "down": DOWN},
        volume={"up": UP, "down": DOWN},
    )
    style = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle="--",
        gridcolor=GRID,
        facecolor=BG,
        figcolor=BG,
        rc={
            "axes.labelcolor": TEXT,
            "axes.edgecolor":  GRID,
            "xtick.color":     TEXT,
            "ytick.color":     TEXT,
            "text.color":      TEXT,
        },
    )

    # ── addplots ──────────────────────────────────────────────────────────────
    ap_list = [
        mpf.make_addplot(ema_view, color=EMA_C, width=1.8),
    ]

    # ── build figure via returnfig so we can annotate ─────────────────────────
    try:
        fig, axes = mpf.plot(
            df,
            type="candle",
            style=style,
            addplot=ap_list,
            volume=True,
            title=f"\n{symbol}  |  4H  |  EMA200 Market Structure",
            ylabel="Price (USDT)",
            ylabel_lower="Volume",
            figratio=(16, 9),
            figscale=1.3,
            returnfig=True,
            warn_too_much_data=500,
        )
    except Exception as e:
        print(f"    [Chart] mplfinance error for {symbol}: {e}")
        plt.close("all")
        return None

    ax   = axes[0]   # price axis
    xlim = ax.get_xlim()
    x0, x1 = xlim

    def hline(ax, price, color, lw=1.0, ls="--", alpha=0.85, zorder=3):
        ax.axhline(price, color=color, linewidth=lw, linestyle=ls,
                   alpha=alpha, zorder=zorder)

    def label(ax, price, text, color, side="right"):
        x = x1 - 0.3 if side == "right" else x0 + 0.3
        ax.text(x, price, f" {text} {_fmt_price(price)}", color=color,
                fontsize=7, va="center", ha="left" if side == "right" else "right",
                zorder=5)

    # ── S/R ───────────────────────────────────────────────────────────────────
    hline(ax, sr.nearest_support,    SUP_C, lw=1.2, ls="--")
    hline(ax, sr.nearest_resistance, RES_C, lw=1.2, ls="--")
    label(ax, sr.nearest_support,    "SUP", SUP_C)
    label(ax, sr.nearest_resistance, "RES", RES_C)

    if sr.major_support != sr.nearest_support:
        hline(ax, sr.major_support,    SUP_C, lw=0.7, ls=":", alpha=0.55)
    if sr.major_resistance != sr.nearest_resistance:
        hline(ax, sr.major_resistance, RES_C, lw=0.7, ls=":", alpha=0.55)

    # ── setup levels ──────────────────────────────────────────────────────────
    if setup:
        # Entry zone shaded band
        ax.axhspan(setup.entry_low, setup.entry_high,
                   alpha=0.15, color=ENTRY_C, zorder=2)
        hline(ax, setup.entry_low,  ENTRY_C, lw=0.9)
        hline(ax, setup.entry_high, ENTRY_C, lw=0.9)
        label(ax, (setup.entry_low + setup.entry_high) / 2, "ENTRY", ENTRY_C)

        hline(ax, setup.stop_loss, SL_C, lw=1.4, ls="-")
        label(ax, setup.stop_loss, "SL", SL_C)

        hline(ax, setup.tp1, TP1_C, lw=1.0)
        hline(ax, setup.tp2, TP2_C, lw=1.0)
        hline(ax, setup.tp3, TP3_C, lw=1.2)
        label(ax, setup.tp1, "TP1", TP1_C)
        label(ax, setup.tp2, "TP2", TP2_C)
        label(ax, setup.tp3, "TP3", TP3_C)

    # ── legend ────────────────────────────────────────────────────────────────
    legend_items = [
        Line2D([0], [0], color=EMA_C,  lw=1.8,            label="EMA200"),
        Line2D([0], [0], color=SUP_C,  lw=1.2, ls="--",   label="Support"),
        Line2D([0], [0], color=RES_C,  lw=1.2, ls="--",   label="Resistance"),
    ]
    if setup:
        legend_items += [
            Line2D([0], [0], color=ENTRY_C, lw=1.0, ls="--", label="Entry Zone"),
            Line2D([0], [0], color=SL_C,    lw=1.4, ls="-",  label="Stop Loss"),
            Line2D([0], [0], color=TP1_C,   lw=1.0, ls="--", label="TP1/TP2/TP3"),
        ]
    ax.legend(
        handles=legend_items, loc="upper left",
        facecolor=PANEL_BG, edgecolor=GRID,
        labelcolor=TEXT, fontsize=8,
    )

    # ── score annotation ──────────────────────────────────────────────────────
    if setup:
        dir_sym = "▲ LONG" if setup.direction == "LONG" else "▼ SHORT"
        ann = (
            f"{dir_sym}  {setup.probability:.0f}% probability\n"
            f"Score {setup.score.total:.0f}/100 — {setup.score.conviction}\n"
            f"R:R  1:{setup.risk_reward:.1f}"
        )
        ax.text(
            0.01, 0.99, ann,
            transform=ax.transAxes, fontsize=8.5,
            verticalalignment="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor=PANEL_BG,
                      alpha=0.9, edgecolor=GRID),
            color=UP if setup.direction == "LONG" else DOWN,
            zorder=10,
        )

    try:
        fig.savefig(
            str(filepath), dpi=130, bbox_inches="tight",
            facecolor=BG, edgecolor="none",
        )
    except Exception as e:
        print(f"    [Chart] save error for {symbol}: {e}")
        plt.close(fig)
        return None

    plt.close(fig)
    return str(filepath)

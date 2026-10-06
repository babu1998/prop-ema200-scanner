"""
1H candle-close scheduler.

Binance 1H candles close at the top of every hour UTC.
The scheduler sleeps until the next close (+10 s buffer), then fires the callback.
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Callable


def _seconds_to_next_1h_close() -> float:
    now = datetime.now(timezone.utc)
    next_close = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    wait = (next_close - now).total_seconds() + 10   # 10 s buffer
    return max(wait, 1)


def run_scheduler(callback: Callable, run_immediately: bool = False) -> None:
    """
    Block forever, calling `callback()` after each 1H candle close.

    Parameters
    ----------
    callback:       function to call (runs the full analysis pipeline)
    run_immediately: if True, also call callback once on startup
    """
    print("Scheduler initialised — waiting for 1H candle close (UTC).")

    if run_immediately:
        print("  Running initial analysis on startup...")
        _safe_call(callback)

    while True:
        wait = _seconds_to_next_1h_close()
        m, s = divmod(int(wait), 60)
        now  = datetime.now(timezone.utc)
        print(f"  [{now:%H:%M:%S UTC}] Next 1H close in {m}m {s}s")
        time.sleep(wait)

        close_time = datetime.now(timezone.utc)
        print(f"\n{'═'*60}")
        print(f"  1H CANDLE CLOSED — {close_time:%Y-%m-%d %H:%M UTC}")
        print(f"{'═'*60}")
        _safe_call(callback)


def _safe_call(fn: Callable) -> None:
    try:
        fn()
    except KeyboardInterrupt:
        raise
    except Exception as e:
        import traceback
        print(f"\n[Scheduler] Callback raised an exception: {e}")
        traceback.print_exc()
        print("[Scheduler] Continuing — will retry at next 4H close.\n")

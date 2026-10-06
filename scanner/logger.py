"""Central logging setup."""
from __future__ import annotations

import logging

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once for the whole application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=_FORMAT,
        datefmt=_DATEFMT,
    )
    # APScheduler is chatty at INFO; keep only its warnings.
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

"""SQLite persistence for snapshots and alerts.

Operations are tiny single-row reads/writes, so the standard-library sqlite3
module guarded by a lock is used instead of an async driver.  All timestamps
are stored as UNIX epoch milliseconds (UTC).
"""
from __future__ import annotations

import sqlite3
import threading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol           TEXT    NOT NULL,
    timestamp        INTEGER NOT NULL,
    price            REAL    NOT NULL,
    funding          REAL    NOT NULL,
    funding_quotient REAL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_ts
    ON snapshots (symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT    NOT NULL,
    timestamp  INTEGER NOT NULL,
    alert_type TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_symbol_ts
    ON alerts (symbol, timestamp DESC);
"""


class Database:
    """Thread-safe wrapper around a single SQLite connection."""

    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ #
    # Snapshots
    # ------------------------------------------------------------------ #

    def insert_snapshot(
        self,
        symbol: str,
        timestamp: int,
        price: float,
        funding: float,
        funding_quotient: float | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots (symbol, timestamp, price, funding,"
                " funding_quotient) VALUES (?, ?, ?, ?, ?)",
                (symbol, timestamp, price, funding, funding_quotient),
            )
            self._conn.commit()

    def last_snapshot(self, symbol: str) -> sqlite3.Row | None:
        """Most recent snapshot for a symbol, or None."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM snapshots WHERE symbol = ?"
                " ORDER BY timestamp DESC LIMIT 1",
                (symbol,),
            )
            return cur.fetchone()

    def snapshots_since(self, since_ms: int) -> list[sqlite3.Row]:
        """All snapshots newer than ``since_ms``, ordered per symbol by time."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM snapshots WHERE timestamp >= ?"
                " ORDER BY symbol ASC, timestamp ASC",
                (since_ms,),
            )
            return cur.fetchall()

    def prune_snapshots(self, older_than_ms: int) -> int:
        """Delete snapshots older than the cutoff; returns rows removed."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM snapshots WHERE timestamp < ?", (older_than_ms,)
            )
            self._conn.commit()
            return cur.rowcount

    # ------------------------------------------------------------------ #
    # Alerts
    # ------------------------------------------------------------------ #

    def insert_alert(self, symbol: str, timestamp: int, alert_type: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO alerts (symbol, timestamp, alert_type)"
                " VALUES (?, ?, ?)",
                (symbol, timestamp, alert_type),
            )
            self._conn.commit()

    def last_alert_ts(self, symbol: str) -> int | None:
        """Timestamp (ms) of the most recent alert for a symbol, or None."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT timestamp FROM alerts WHERE symbol = ?"
                " ORDER BY timestamp DESC LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            return int(row["timestamp"]) if row else None

"""Optional Prometheus metrics endpoint (bonus module).

Enabled with METRICS_ENABLED=true; exposes metrics on METRICS_PORT.
Degrades to a no-op if prometheus-client is not installed.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("metrics")

try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server

    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on environment
    PROMETHEUS_AVAILABLE = False


class Metrics:
    """Facade over prometheus-client; all methods are safe no-ops when
    the library is missing or metrics are disabled."""

    def __init__(self, enabled: bool, port: int) -> None:
        self._active = enabled and PROMETHEUS_AVAILABLE
        if enabled and not PROMETHEUS_AVAILABLE:
            logger.warning(
                "METRICS_ENABLED=true but prometheus-client is not installed"
            )
        if not self._active:
            return

        start_http_server(port)
        logger.info("Prometheus metrics listening on :%d", port)
        self._scans = Counter(
            "scanner_scans_total", "Completed scan cycles"
        )
        self._alerts = Counter(
            "scanner_alerts_total", "Alerts sent", ["alert_type"]
        )
        self._errors = Counter(
            "scanner_api_errors_total", "Binance API failures"
        )
        self._duration = Histogram(
            "scanner_scan_duration_seconds", "Scan cycle duration"
        )
        self._monitored = Gauge(
            "scanner_monitored_symbols", "Symbols currently monitored"
        )

    def scan_completed(self, duration_seconds: float) -> None:
        if self._active:
            self._scans.inc()
            self._duration.observe(duration_seconds)

    def alert_sent(self, alert_type: str) -> None:
        if self._active:
            self._alerts.labels(alert_type=alert_type).inc()

    def api_error(self) -> None:
        if self._active:
            self._errors.inc()

    def set_monitored(self, count: int) -> None:
        if self._active:
            self._monitored.set(count)

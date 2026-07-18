from __future__ import annotations

import logging
from threading import Lock
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send


EXCLUDED_PATHS = {"/healthz", "/api/healthz", "/api/metrics"}
LOGGER = logging.getLogger(__name__)


class RequestMetrics:
    """Small process-local request aggregate for Prometheus exposition."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._requests_total = 0
        self._errors_total = 0
        self._duration_seconds_sum = 0.0
        self._slow_requests_total = 0

    def observe(self, *, status_code: int, duration_ms: float, slow: bool) -> None:
        with self._lock:
            self._requests_total += 1
            if status_code >= 500:
                self._errors_total += 1
            self._duration_seconds_sum += duration_ms / 1000
            if slow:
                self._slow_requests_total += 1

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "requests_total": self._requests_total,
                "errors_total": self._errors_total,
                "duration_seconds_sum": self._duration_seconds_sum,
                "slow_requests_total": self._slow_requests_total,
            }


class RequestTimingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        slow_request_ms: int,
        logger: logging.Logger = LOGGER,
        metrics: RequestMetrics | None = None,
    ) -> None:
        self.app = app
        self.slow_request_ms = slow_request_ms
        self.logger = logger
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        if path in EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method") or "UNKNOWN")
        status_code = 500
        started_at = perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (perf_counter() - started_at) * 1000
            level = logging.INFO
            if self.slow_request_ms > 0 and duration_ms >= self.slow_request_ms:
                level = logging.WARNING
            if self.metrics is not None:
                self.metrics.observe(
                    status_code=status_code,
                    duration_ms=duration_ms,
                    slow=level == logging.WARNING,
                )
            self.logger.log(
                level,
                "request method=%s path=%s status=%s duration_ms=%.1f",
                method,
                path,
                status_code,
                duration_ms,
            )

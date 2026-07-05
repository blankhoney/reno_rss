from __future__ import annotations

import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send


EXCLUDED_PATHS = {"/healthz", "/api/healthz"}
LOGGER = logging.getLogger(__name__)


class RequestTimingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        slow_request_ms: int,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.app = app
        self.slow_request_ms = slow_request_ms
        self.logger = logger

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
            self.logger.log(
                level,
                "request method=%s path=%s status=%s duration_ms=%.1f",
                method,
                path,
                status_code,
                duration_ms,
            )

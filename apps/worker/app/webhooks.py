"""Signed, fail-soft outbound webhook delivery for worker events."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from typing import Any
from urllib import error, request


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class WebhookClient:
    """POST event envelopes without allowing delivery failure to stop jobs."""

    def __init__(
        self,
        url: str,
        *,
        secret: str | None = None,
        timeout_seconds: float = 5.0,
        opener: Any | None = None,
    ) -> None:
        self.url = url.strip()
        self.secret = secret
        self.timeout_seconds = timeout_seconds
        self.opener = opener

    def emit(self, event: str, payload: Mapping[str, object]) -> dict[str, object]:
        envelope = {
            "event": event,
            "generated_at": datetime.now(UTC).isoformat(),
            "payload": dict(payload),
        }
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "ai-reader-webhook/1.0",
            "X-AI-Reader-Event": event,
        }
        if self.secret:
            headers["X-AI-Reader-Signature"] = sign_payload(self.secret, body)
        outbound = request.Request(
            self.url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            if self.opener is None:
                response_context = request.urlopen(
                    outbound,
                    timeout=self.timeout_seconds,
                )
            else:
                response_context = self.opener.open(
                    outbound,
                    self.timeout_seconds,
                )
            with response_context as response:
                status = getattr(response, "status", None) or response.getcode()
            status_code = int(status) if status is not None else None
            ok = status_code is not None and 200 <= status_code < 300
            return {
                "ok": ok,
                "event": event,
                "status_code": status_code,
                "error": None if ok else "http_error",
            }
        except error.HTTPError as exc:
            return {
                "ok": False,
                "event": event,
                "status_code": int(exc.code),
                "error": str(exc.reason),
            }
        except Exception as exc:
            return {
                "ok": False,
                "event": event,
                "status_code": None,
                "error": str(exc),
            }


def webhook_client_from_env() -> WebhookClient | None:
    url = (os.environ.get("AI_READER_WEBHOOK_URL") or "").strip()
    if not url:
        return None
    secret = (os.environ.get("AI_READER_WEBHOOK_SECRET") or "").strip() or None
    timeout = float(os.environ.get("AI_READER_WEBHOOK_TIMEOUT_SECONDS", "5"))
    return WebhookClient(url, secret=secret, timeout_seconds=timeout)

"""Optional outbound webhooks for brief / high-score events (GOAL §4.E)."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class WebhookDelivery:
    url: str
    event: str
    status_code: int | None
    ok: bool
    error: str | None = None


def sign_payload(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_webhook_envelope(
    event: str,
    payload: Mapping[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    stamp = (generated_at or datetime.now(UTC)).astimezone(UTC)
    return {
        "event": event,
        "generated_at": stamp.isoformat(),
        "payload": dict(payload),
    }


def deliver_webhook(
    url: str,
    event: str,
    payload: Mapping[str, Any],
    *,
    secret: str | None = None,
    timeout_seconds: float = 5.0,
    opener=None,
) -> WebhookDelivery:
    """POST signed JSON. Failures are returned, never raised (pipeline must continue)."""
    if not url or not str(url).strip():
        return WebhookDelivery(url=url, event=event, status_code=None, ok=False, error="empty_url")
    envelope = build_webhook_envelope(event, payload)
    body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "ai-reader-webhook/1.0",
        "X-AI-Reader-Event": event,
    }
    if secret:
        headers["X-AI-Reader-Signature"] = sign_payload(secret, body)
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        if opener is not None:
            with opener.open(req, timeout=timeout_seconds) as response:
                status = getattr(response, "status", None) or response.getcode()
        else:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                status = getattr(response, "status", None) or response.getcode()
        code = int(status) if status is not None else None
        ok = code is not None and 200 <= code < 300
        return WebhookDelivery(url=url, event=event, status_code=code, ok=ok, error=None if ok else "http_error")
    except error.HTTPError as exc:
        return WebhookDelivery(
            url=url,
            event=event,
            status_code=int(exc.code),
            ok=False,
            error=str(exc.reason),
        )
    except Exception as exc:  # network / timeout
        return WebhookDelivery(url=url, event=event, status_code=None, ok=False, error=str(exc))

"""
Scorer Worker entry point.

The worker runs as an internal HTTP service:
  - GET /healthz
  - POST /internal/score-entry
  - POST /webhooks/miniflux

Scoring is event-driven. There is no background polling loop.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import os
from typing import Any

import psycopg2

from miniflux_client import MinifluxClient
from repository import get_latest_score, get_scoring_settings, init_schema, upsert_score, upsert_snapshot
from scoring import score_entry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MINIFLUX_API_BASE_URL = os.environ["MINIFLUX_API_BASE_URL"]
MINIFLUX_USERNAME = os.environ["MINIFLUX_USERNAME"]
MINIFLUX_PASSWORD = os.environ["MINIFLUX_PASSWORD"]
SCORING_DATABASE_URL = os.environ["SCORING_DATABASE_URL"]
SCORER_TENANT_ID = os.getenv("SCORER_TENANT_ID", "default")
SCORER_PORT = int(os.getenv("SCORER_PORT", "8000"))
SCORER_WEBHOOK_USERNAME = os.getenv("SCORER_WEBHOOK_USERNAME", "")
SCORER_WEBHOOK_PASSWORD = os.getenv("SCORER_WEBHOOK_PASSWORD", "")
SCORER_WEBHOOK_MAX_ENTRIES = int(os.getenv("SCORER_WEBHOOK_MAX_ENTRIES", "20"))


def content_hash_for_entry(entry: dict) -> str:
    content = (entry.get("title") or "") + " " + (entry.get("content") or "")
    return hashlib.sha256(content.strip().encode()).hexdigest()


def score_miniflux_entry(
    conn: psycopg2.extensions.connection,
    entry: dict,
    *,
    force: bool,
) -> dict:
    content_hash = content_hash_for_entry(entry)
    miniflux_entry_id = int(entry["id"])

    upsert_snapshot(
        conn,
        {
            "tenant_id": SCORER_TENANT_ID,
            "miniflux_entry_id": miniflux_entry_id,
            "feed_id": entry.get("feed_id"),
            "title": entry.get("title"),
            "url": entry.get("url"),
            "published_at": entry.get("published_at"),
            "content_hash": content_hash,
        },
    )

    if not force:
        cached = get_latest_score(conn, SCORER_TENANT_ID, miniflux_entry_id, content_hash)
        if cached is not None:
            return {
                "ok": True,
                "entryId": miniflux_entry_id,
                "score": cached["score"],
                "cached": True,
            }

    payload = score_entry(entry)
    upsert_score(
        conn,
        {
            "tenant_id": SCORER_TENANT_ID,
            "miniflux_entry_id": miniflux_entry_id,
            "content_hash": content_hash,
            **payload,
            "tags": payload["tags"],
        },
    )
    return {"ok": True, "entryId": miniflux_entry_id, "score": payload["score"], "cached": False}


def score_entry_by_id(
    conn: psycopg2.extensions.connection,
    entry_id: int,
    *,
    force: bool,
) -> dict:
    client = MinifluxClient(MINIFLUX_API_BASE_URL, MINIFLUX_USERNAME, MINIFLUX_PASSWORD)
    entry = client.get_entry(entry_id)
    if entry is None:
        return {"ok": False, "entryId": entry_id, "error": "entry_not_found"}
    return score_miniflux_entry(conn, entry, force=force)


def handle_score_entry_request(conn: psycopg2.extensions.connection, payload: Any) -> tuple[int, dict]:
    if not isinstance(payload, dict):
        return 400, {"ok": False, "error": "invalid_body"}

    entry_id = payload.get("entryId")
    if not isinstance(entry_id, int) or entry_id <= 0:
        return 400, {"ok": False, "error": "invalid_entry_id"}

    result = score_entry_by_id(conn, entry_id, force=bool(payload.get("force", False)))
    if not result.get("ok") and result.get("error") == "entry_not_found":
        return 404, result
    return 200, result


def handle_miniflux_webhook(
    conn: psycopg2.extensions.connection,
    event_type: str | None,
    payload: Any,
) -> dict:
    if event_type != "new_entries":
        return {"ok": True, "eventType": event_type, "processed": 0, "skipped": 0}

    settings = get_scoring_settings(conn, SCORER_TENANT_ID)
    entries = extract_webhook_entries(payload)
    if not settings["auto_score_new_unread"]:
        return {
            "ok": True,
            "eventType": event_type,
            "processed": 0,
            "skipped": len(entries),
        }

    max_entries = max(1, min(100, int(settings.get("webhook_max_entries") or SCORER_WEBHOOK_MAX_ENTRIES)))
    candidate_ids: list[int] = []
    skipped = 0
    for entry in entries:
        status = entry.get("status")
        if status is not None and status != "unread":
            skipped += 1
            continue

        entry_id = parse_positive_int(entry.get("id"))
        if entry_id is None:
            skipped += 1
            continue
        candidate_ids.append(entry_id)

    selected_ids = candidate_ids[:max_entries]
    skipped += len(candidate_ids) - len(selected_ids)
    for entry_id in selected_ids:
        score_entry_by_id(conn, entry_id, force=False)

    return {
        "ok": True,
        "eventType": event_type,
        "processed": len(selected_ids),
        "skipped": skipped,
    }


def extract_webhook_entries(payload: Any) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    entries = payload.get("entries")
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]
    entry = payload.get("entry")
    if isinstance(entry, dict):
        return [entry]
    entry_ids = payload.get("entry_ids")
    if isinstance(entry_ids, list):
        return [{"id": entry_id, "status": "unread"} for entry_id in entry_ids]
    return []


def parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def check_basic_auth(header: str | None, username: str, password: str) -> bool:
    if not username and not password:
        return True
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.removeprefix("Basic "), validate=True).decode()
    except (ValueError, UnicodeDecodeError):
        return False
    candidate_user, separator, candidate_password = decoded.partition(":")
    if separator != ":":
        return False
    return hmac.compare_digest(candidate_user, username) and hmac.compare_digest(
        candidate_password,
        password,
    )


class ScorerRequestHandler(BaseHTTPRequestHandler):
    server_version = "scorer-worker/0.1"

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self.write_json(200, {"ok": True, "time": datetime.now(UTC).isoformat()})
            return
        self.write_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if not check_basic_auth(
            self.headers.get("Authorization"),
            SCORER_WEBHOOK_USERNAME,
            SCORER_WEBHOOK_PASSWORD,
        ):
            self.write_json(401, {"ok": False, "error": "unauthorized"})
            return

        payload = self.read_json_body()
        if payload is None:
            self.write_json(400, {"ok": False, "error": "invalid_json"})
            return

        conn = psycopg2.connect(SCORING_DATABASE_URL)
        try:
            if self.path == "/internal/score-entry":
                status, result = handle_score_entry_request(conn, payload)
                self.write_json(status, result)
                return
            if self.path == "/webhooks/miniflux":
                result = handle_miniflux_webhook(
                    conn,
                    self.headers.get("X-Miniflux-Event-Type"),
                    payload,
                )
                self.write_json(202, result)
                return
            self.write_json(404, {"ok": False, "error": "not_found"})
        finally:
            conn.close()

    def read_json_body(self) -> Any | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length < 0 or length > 1_000_000:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode() if raw else "{}")
        except json.JSONDecodeError:
            return None

    def write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        log.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    log.info("Scorer service starting (port=%d)", SCORER_PORT)
    conn = psycopg2.connect(SCORING_DATABASE_URL)
    try:
        init_schema(conn)
    finally:
        conn.close()

    server = ThreadingHTTPServer(("0.0.0.0", SCORER_PORT), ScorerRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()

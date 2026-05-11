"""
Scorer Worker entry point.

Internal scheduling loop:
  1. Fetch recent entries from Miniflux API
  2. Upsert items_snapshot
  3. Score unscored entries
  4. Upsert item_scores
  5. Sleep SCORER_INTERVAL_SECONDS
"""

from __future__ import annotations

import hashlib
import logging
import os
import time

import psycopg2

from miniflux_client import MinifluxClient
from repository import upsert_score, upsert_snapshot, init_schema
from scoring import score_entry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MINIFLUX_API_BASE_URL = os.environ["MINIFLUX_API_BASE_URL"]
MINIFLUX_API_KEY = os.environ["MINIFLUX_API_KEY"]
SCORING_DATABASE_URL = os.environ["SCORING_DATABASE_URL"]
SCORER_INTERVAL_SECONDS = int(os.getenv("SCORER_INTERVAL_SECONDS", "3600"))
SCORER_TENANT_ID = os.getenv("SCORER_TENANT_ID", "default")


def run_once(conn: psycopg2.extensions.connection) -> None:
    client = MinifluxClient(MINIFLUX_API_BASE_URL, MINIFLUX_API_KEY)
    entries = client.get_recent_entries()
    log.info("Fetched %d entries from Miniflux", len(entries))

    for entry in entries:
        content = (entry.get("title") or "") + " " + (entry.get("content") or "")
        content_hash = hashlib.sha256(content.strip().encode()).hexdigest()

        snapshot_row = {
            "tenant_id": SCORER_TENANT_ID,
            "miniflux_entry_id": entry["id"],
            "feed_id": entry.get("feed_id"),
            "title": entry.get("title"),
            "url": entry.get("url"),
            "published_at": entry.get("published_at"),
            "content_hash": content_hash,
        }
        upsert_snapshot(conn, snapshot_row)

        payload = score_entry(entry)
        score_row = {
            "tenant_id": SCORER_TENANT_ID,
            "miniflux_entry_id": entry["id"],
            "content_hash": content_hash,
            **payload,
            "tags": payload["tags"],  # will be serialized to JSON in repository
        }
        upsert_score(conn, score_row)

    log.info("Scoring cycle complete")


def main() -> None:
    log.info("Scorer worker starting (interval=%ds)", SCORER_INTERVAL_SECONDS)
    conn = psycopg2.connect(SCORING_DATABASE_URL)
    init_schema(conn)

    while True:
        try:
            run_once(conn)
        except Exception as exc:  # noqa: BLE001
            log.error("Scoring cycle failed: %s", exc)
        time.sleep(SCORER_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

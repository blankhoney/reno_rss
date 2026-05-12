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

from datetime import UTC, datetime
import hashlib
import logging
import os
import time

import psycopg2

from miniflux_client import MinifluxClient
from repository import create_digest, init_schema, upsert_digest_item, upsert_score, upsert_snapshot
from scoring import score_entry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MINIFLUX_API_BASE_URL = os.environ["MINIFLUX_API_BASE_URL"]
MINIFLUX_API_KEY = os.environ["MINIFLUX_API_KEY"]
SCORING_DATABASE_URL = os.environ["SCORING_DATABASE_URL"]
SCORER_INTERVAL_SECONDS = int(os.getenv("SCORER_INTERVAL_SECONDS", "3600"))
SCORER_TENANT_ID = os.getenv("SCORER_TENANT_ID", "default")
DIGEST_MIN_SCORE = int(os.getenv("DIGEST_MIN_SCORE", "70"))
DIGEST_MAX_ITEMS = int(os.getenv("DIGEST_MAX_ITEMS", "10"))


def run_once(conn: psycopg2.extensions.connection) -> None:
    window_start = datetime.now(UTC)
    client = MinifluxClient(MINIFLUX_API_BASE_URL, MINIFLUX_API_KEY)
    entries = client.get_recent_entries()
    log.info("Fetched %d entries from Miniflux", len(entries))

    scored_entries = []
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
        scored_entries.append({"entry": entry, "score_row": score_row})

    digest_count = _create_digest_from_scores(conn, scored_entries, window_start, datetime.now(UTC))
    log.info("Scoring cycle complete (digest_items=%d)", digest_count)


def _create_digest_from_scores(
    conn: psycopg2.extensions.connection,
    scored_entries: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> int:
    selected = [
        item
        for item in scored_entries
        if int(item["score_row"]["score"]) >= DIGEST_MIN_SCORE
    ]
    selected = sorted(selected, key=lambda item: item["score_row"]["score"], reverse=True)[
        :DIGEST_MAX_ITEMS
    ]
    if not selected:
        log.info("Digest skipped (eligible_items=0)")
        return 0

    first_score = selected[0]["score_row"]
    digest_id = create_digest(
        conn,
        {
            "tenant_id": SCORER_TENANT_ID,
            "window_start": window_start,
            "window_end": window_end,
            "title": f"RSS digest {window_end:%Y-%m-%d %H:%M UTC}",
            "summary": f"{len(selected)} items selected from {len(scored_entries)} scored entries.",
            "model_provider": first_score["model_provider"],
            "model_name": first_score["model_name"],
            "model_version": first_score["model_version"],
            "prompt_version": first_score["prompt_version"],
            "status": "success",
        },
    )

    for index, item in enumerate(selected, start=1):
        entry = item["entry"]
        score_row = item["score_row"]
        upsert_digest_item(
            conn,
            {
                "digest_id": digest_id,
                "tenant_id": SCORER_TENANT_ID,
                "miniflux_entry_id": entry["id"],
                "rank": index,
                "score": score_row["score"],
                "title": entry.get("title"),
                "url": entry.get("url"),
                "reason": score_row["reason"],
            },
        )

    log.info("Digest created (digest_id=%s, items=%d)", digest_id, len(selected))
    return len(selected)


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

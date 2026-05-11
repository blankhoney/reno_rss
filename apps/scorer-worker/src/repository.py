"""
Repository layer: idempotent writes to the scoring database.

All write functions use ON CONFLICT … DO UPDATE so that re-running the
scorer for the same entry is safe and deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

import psycopg2


_SCHEMA_SQL = (Path(__file__).parent.parent / "sql" / "001_init_scoring.sql").read_text()


def init_schema(conn: psycopg2.extensions.connection) -> None:
    """Apply DDL (idempotent — safe to call on every startup)."""
    with conn.cursor() as cur:
        cur.execute(_SCHEMA_SQL)
    conn.commit()


def upsert_snapshot(conn: psycopg2.extensions.connection, row: dict) -> None:
    """Insert or update an items_snapshot row."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO items_snapshot
                (tenant_id, miniflux_entry_id, feed_id, title, url,
                 published_at, content_hash)
            VALUES
                (%(tenant_id)s, %(miniflux_entry_id)s, %(feed_id)s, %(title)s,
                 %(url)s, %(published_at)s, %(content_hash)s)
            ON CONFLICT (tenant_id, miniflux_entry_id)
            DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                title        = EXCLUDED.title,
                url          = EXCLUDED.url,
                published_at = EXCLUDED.published_at,
                fetched_at   = NOW();
            """,
            row,
        )
    conn.commit()


def upsert_score(conn: psycopg2.extensions.connection, row: dict) -> None:
    """Insert or update an item_scores row (idempotent on content_hash + model_version)."""
    # Serialize tags list → JSON string for psycopg2
    serialized = dict(row)
    if isinstance(serialized.get("tags"), list):
        serialized["tags"] = json.dumps(serialized["tags"])

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO item_scores (
                tenant_id, miniflux_entry_id, content_hash,
                score, tags, reason, model_version,
                model_provider, model_name, prompt_version,
                confidence, scoring_status, error_message
            ) VALUES (
                %(tenant_id)s, %(miniflux_entry_id)s, %(content_hash)s,
                %(score)s, %(tags)s::jsonb, %(reason)s, %(model_version)s,
                %(model_provider)s, %(model_name)s, %(prompt_version)s,
                %(confidence)s, %(scoring_status)s, %(error_message)s
            )
            ON CONFLICT (tenant_id, miniflux_entry_id, content_hash, model_version)
            DO UPDATE SET
                score          = EXCLUDED.score,
                tags           = EXCLUDED.tags,
                reason         = EXCLUDED.reason,
                confidence     = EXCLUDED.confidence,
                scoring_status = EXCLUDED.scoring_status,
                error_message  = EXCLUDED.error_message,
                scored_at      = NOW();
            """,
            serialized,
        )
    conn.commit()

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
    if isinstance(serialized.get("dimension_scores"), dict):
        serialized["dimension_scores"] = json.dumps(serialized["dimension_scores"])
    if not serialized.get("dimension_scores"):
        serialized["dimension_scores"] = json.dumps({})

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO item_scores (
                tenant_id, miniflux_entry_id, content_hash,
                score, dimension_scores, tags, reason, model_version,
                model_provider, model_name, prompt_version,
                confidence, scoring_status, error_message
            ) VALUES (
                %(tenant_id)s, %(miniflux_entry_id)s, %(content_hash)s,
                %(score)s, %(dimension_scores)s::jsonb, %(tags)s::jsonb, %(reason)s, %(model_version)s,
                %(model_provider)s, %(model_name)s, %(prompt_version)s,
                %(confidence)s, %(scoring_status)s, %(error_message)s
            )
            ON CONFLICT (tenant_id, miniflux_entry_id, content_hash, model_version)
            DO UPDATE SET
                score            = EXCLUDED.score,
                dimension_scores = EXCLUDED.dimension_scores,
                tags             = EXCLUDED.tags,
                reason           = EXCLUDED.reason,
                confidence       = EXCLUDED.confidence,
                scoring_status   = EXCLUDED.scoring_status,
                error_message    = EXCLUDED.error_message,
                scored_at        = NOW();
            """,
            serialized,
        )
    conn.commit()


def create_digest(conn: psycopg2.extensions.connection, row: dict) -> int:
    """Create or update one digest batch and return its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO digests (
                tenant_id, window_start, window_end, title, summary,
                model_provider, model_name, model_version, prompt_version, status
            ) VALUES (
                %(tenant_id)s, %(window_start)s, %(window_end)s, %(title)s, %(summary)s,
                %(model_provider)s, %(model_name)s, %(model_version)s, %(prompt_version)s,
                %(status)s
            )
            ON CONFLICT (tenant_id, window_start, window_end, prompt_version)
            DO UPDATE SET
                title          = EXCLUDED.title,
                summary        = EXCLUDED.summary,
                model_provider = EXCLUDED.model_provider,
                model_name     = EXCLUDED.model_name,
                model_version  = EXCLUDED.model_version,
                status         = EXCLUDED.status
            RETURNING id;
            """,
            row,
        )
        digest_id = cur.fetchone()[0]
    conn.commit()
    return digest_id


def upsert_digest_item(conn: psycopg2.extensions.connection, row: dict) -> None:
    """Insert or update an item selected for a digest."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO digest_items (
                digest_id, tenant_id, miniflux_entry_id, rank, score, title, url, reason
            ) VALUES (
                %(digest_id)s, %(tenant_id)s, %(miniflux_entry_id)s, %(rank)s,
                %(score)s, %(title)s, %(url)s, %(reason)s
            )
            ON CONFLICT (digest_id, tenant_id, miniflux_entry_id)
            DO UPDATE SET
                rank   = EXCLUDED.rank,
                score  = EXCLUDED.score,
                title  = EXCLUDED.title,
                url    = EXCLUDED.url,
                reason = EXCLUDED.reason;
            """,
            row,
        )
    conn.commit()

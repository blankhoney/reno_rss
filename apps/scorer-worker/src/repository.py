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

DEFAULT_SCORING_SETTINGS = {
    "auto_score_new_unread": True,
    "webhook_max_entries": 20,
    "manual_batch_size": 20,
    "manual_rescore_enabled": True,
}


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
    if isinstance(serialized.get("dimension_reasons"), dict):
        serialized["dimension_reasons"] = json.dumps(serialized["dimension_reasons"])
    if not serialized.get("dimension_reasons"):
        serialized["dimension_reasons"] = json.dumps({})
    serialized.setdefault("summary_zh", "")
    serialized.setdefault("summary_original", "")
    serialized.setdefault("source_language", "unknown")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO item_scores (
                tenant_id, miniflux_entry_id, content_hash,
                score, dimension_scores, tags, reason,
                summary_zh, summary_original, source_language, dimension_reasons,
                model_version, model_provider, model_name, prompt_version,
                confidence, scoring_status, error_message
            ) VALUES (
                %(tenant_id)s, %(miniflux_entry_id)s, %(content_hash)s,
                %(score)s, %(dimension_scores)s::jsonb, %(tags)s::jsonb, %(reason)s,
                %(summary_zh)s, %(summary_original)s, %(source_language)s, %(dimension_reasons)s::jsonb,
                %(model_version)s, %(model_provider)s, %(model_name)s, %(prompt_version)s,
                %(confidence)s, %(scoring_status)s, %(error_message)s
            )
            ON CONFLICT (tenant_id, miniflux_entry_id, content_hash, model_version)
            DO UPDATE SET
                score            = EXCLUDED.score,
                dimension_scores = EXCLUDED.dimension_scores,
                tags             = EXCLUDED.tags,
                reason           = EXCLUDED.reason,
                summary_zh       = EXCLUDED.summary_zh,
                summary_original = EXCLUDED.summary_original,
                source_language  = EXCLUDED.source_language,
                dimension_reasons = EXCLUDED.dimension_reasons,
                confidence       = EXCLUDED.confidence,
                scoring_status   = EXCLUDED.scoring_status,
                error_message    = EXCLUDED.error_message,
                scored_at        = NOW();
            """,
            serialized,
        )
    conn.commit()


def get_latest_score(
    conn: psycopg2.extensions.connection,
    tenant_id: str,
    miniflux_entry_id: int,
    content_hash: str | None = None,
) -> dict | None:
    """Return the latest score for an entry, optionally constrained to one content hash."""
    if content_hash is None:
        where_hash = ""
        values: tuple = (tenant_id, miniflux_entry_id)
    else:
        where_hash = "AND content_hash = %s"
        values = (tenant_id, miniflux_entry_id, content_hash)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT score, scored_at
            FROM item_scores
            WHERE tenant_id = %s
              AND miniflux_entry_id = %s
              {where_hash}
            ORDER BY scored_at DESC
            LIMIT 1
            """,
            values,
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {"score": int(row[0]), "scored_at": row[1]}


def get_scoring_settings(conn: psycopg2.extensions.connection, tenant_id: str) -> dict:
    """Return scoring settings for a tenant, falling back to defaults."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT auto_score_new_unread, webhook_max_entries, manual_batch_size,
                   manual_rescore_enabled
            FROM scoring_settings
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
    if row is None:
        return dict(DEFAULT_SCORING_SETTINGS)
    return {
        "auto_score_new_unread": bool(row[0]),
        "webhook_max_entries": int(row[1]),
        "manual_batch_size": int(row[2]),
        "manual_rescore_enabled": bool(row[3]),
    }


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

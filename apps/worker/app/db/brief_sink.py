"""Persist daily intelligence briefs; falls back to jobs.result when no table."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, text


class DatabaseBriefSink:
    def __init__(self, database_url: str | None = None, *, engine: Engine | None = None) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def list_latest_recommendation_items(self, *, limit: int = 10) -> list[dict[str, object]]:
        with self.engine.begin() as connection:
            edition_id = connection.execute(
                text(
                    """
                    SELECT id FROM recommendation_editions
                    ORDER BY generated_at DESC, id DESC
                    LIMIT 1
                    """
                )
            ).scalar_one_or_none()
            if edition_id is None:
                return []
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT
                          i.article_id,
                          i.rank,
                          i.rank_score,
                          i.tier,
                          i.reason,
                          a.title,
                          a.content_quality,
                          s.summary_zh,
                          s.base_score AS overall_score,
                          s.risk_flags,
                          s.dimension_scores
                        FROM recommendation_items i
                        LEFT JOIN articles a ON a.id = i.article_id
                        LEFT JOIN article_base_scores s
                          ON s.article_id = i.article_id AND s.is_active = true
                        WHERE i.edition_id = :edition_id
                        ORDER BY i.rank ASC
                        LIMIT :limit
                        """
                    ),
                    {"edition_id": edition_id, "limit": limit},
                )
                .mappings()
                .all()
            )
        items: list[dict[str, object]] = []
        for row in rows:
            item = dict(row)
            risk_flags = item.get("risk_flags")
            if isinstance(risk_flags, str):
                try:
                    risk_flags = json.loads(risk_flags)
                except json.JSONDecodeError:
                    risk_flags = []
            if not isinstance(risk_flags, list):
                risk_flags = []
            item["risk_flags"] = risk_flags
            dims = item.get("dimension_scores")
            if isinstance(dims, str):
                try:
                    dims = json.loads(dims)
                except json.JSONDecodeError:
                    dims = {}
            source_quality = None
            if isinstance(dims, dict) and dims.get("source_quality") is not None:
                try:
                    source_quality = float(dims["source_quality"])
                except (TypeError, ValueError):
                    source_quality = None
            item["source_quality"] = source_quality
            items.append(item)
        return items

    def save_daily_brief(self, brief: dict[str, object]) -> int:
        # Store as a completed jobs row so no new table is required for v1.
        payload = json.dumps({"kind": "daily_brief"}, ensure_ascii=False)
        result = json.dumps(brief, ensure_ascii=False)
        now = datetime.now(UTC).isoformat()
        dedupe = f"brief:daily:{brief.get('generated_at', now)[:10]}"
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                row_id = connection.execute(
                    text(
                        """
                        INSERT INTO jobs (
                          job_type, status, payload, dedupe_key, result, completed_at, created_at, updated_at
                        )
                        VALUES (
                          'generate_daily_brief', 'succeeded',
                          CAST(:payload AS jsonb), :dedupe_key, CAST(:result AS jsonb),
                          :now, :now, :now
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "payload": payload,
                        "dedupe_key": dedupe,
                        "result": result,
                        "now": now,
                    },
                ).scalar_one()
            else:
                row_id = connection.execute(
                    text(
                        """
                        INSERT INTO jobs (
                          job_type, status, payload, dedupe_key, result, completed_at
                        )
                        VALUES (
                          'generate_daily_brief', 'succeeded',
                          :payload, :dedupe_key, :result, :now
                        )
                        """
                    ),
                    {
                        "payload": payload,
                        "dedupe_key": dedupe,
                        "result": result,
                        "now": now,
                    },
                ).lastrowid
        return int(row_id)

    def dispose(self) -> None:
        self.engine.dispose()

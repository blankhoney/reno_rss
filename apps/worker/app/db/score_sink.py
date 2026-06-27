from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from sqlalchemy import Engine, create_engine, text


RECOMMENDATIONS_JOB_TYPE = "generate_recommendations"


class DatabaseScoreSink:
    def __init__(self, database_url: str | None = None, *, engine: Engine | None = None) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def list_batch_articles(self, batch_id: object) -> list[dict[str, object]]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT
                            a.id,
                            a.title,
                            a.url,
                            a.content_text,
                            a.content_html,
                            a.content_hash
                        FROM scoring_batch_items i
                        JOIN articles a ON a.id = i.article_id
                        WHERE i.batch_id = :batch_id
                        ORDER BY i.id ASC;
                        """
                    ),
                    {"batch_id": batch_id},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def save_score(self, article_id: object, score: dict[str, object]) -> int:
        is_success = score.get("scoring_status") == "success"
        values = _score_values(article_id, score, is_active=is_success)
        with self.engine.begin() as connection:
            if is_success:
                connection.execute(
                    text(
                        """
                        UPDATE article_base_scores
                        SET is_active = FALSE
                        WHERE article_id = :article_id AND is_active = TRUE;
                        """
                    ),
                    {"article_id": article_id},
                )
            row = (
                connection.execute(
                    text(_insert_score_sql(self.engine.dialect.name)),
                    values,
                )
                .mappings()
                .one()
            )
            score_id = int(row["id"])
            connection.execute(
                text(
                    """
                    UPDATE scoring_batch_items
                    SET status = :status,
                        base_score_id = :base_score_id,
                        error = :error
                    WHERE batch_id = :batch_id AND article_id = :article_id;
                    """
                ),
                {
                    "status": "scored" if is_success else "error",
                    "base_score_id": score_id,
                    "error": None if is_success else values["error"],
                    "batch_id": values["batch_id"],
                    "article_id": article_id,
                },
            )
        return score_id

    def finish_batch(self, batch_id: object) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE scoring_batches
                    SET status='done', finished_at=:finished_at
                    WHERE id=:batch_id;
                    """
                ),
                {"batch_id": batch_id, "finished_at": datetime.now(UTC).isoformat()},
            )

    def enqueue_recommendations(self, batch_id: object) -> None:
        payload = {"source_batch_id": batch_id}
        params = {
            "job_type": RECOMMENDATIONS_JOB_TYPE,
            "payload": json.dumps(payload, ensure_ascii=False),
            "dedupe_key": _dedupe_key_for(RECOMMENDATIONS_JOB_TYPE, batch_id),
        }
        with self.engine.begin() as connection:
            existing = connection.execute(
                text(
                    """
                    SELECT id
                    FROM jobs
                    WHERE job_type=:job_type
                      AND dedupe_key=:dedupe_key
                      AND status IN ('queued', 'running')
                    LIMIT 1;
                    """
                ),
                params,
            ).scalar_one_or_none()
            if existing is not None:
                return

            if self.engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        """
                        INSERT INTO jobs (job_type, payload, dedupe_key)
                        VALUES (:job_type, CAST(:payload AS jsonb), :dedupe_key)
                        ON CONFLICT (job_type, dedupe_key)
                        WHERE status IN ('queued', 'running')
                        DO NOTHING;
                        """
                    ),
                    params,
                )
                return

            connection.execute(
                text(
                    """
                    INSERT INTO jobs (job_type, payload, dedupe_key)
                    VALUES (:job_type, :payload, :dedupe_key);
                    """
                ),
                params,
            )

    def dispose(self) -> None:
        self.engine.dispose()


def _score_values(
    article_id: object,
    score: dict[str, object],
    *,
    is_active: bool,
) -> dict[str, object]:
    return {
        "article_id": article_id,
        "batch_id": score["batch_id"],
        "base_score": int(score["base_score"]),
        "recommendation_tier": str(score["recommendation_tier"]),
        "summary_zh": str(score.get("summary_zh", "")),
        "summary_original": str(score.get("summary_original", "")),
        "source_language": str(score.get("source_language", "unknown")),
        "dimension_scores": json.dumps(score.get("dimension_scores", {}), ensure_ascii=False),
        "dimension_reasons": json.dumps(score.get("dimension_reasons", {}), ensure_ascii=False),
        "tags": json.dumps(score.get("tags", []), ensure_ascii=False),
        "reason": str(score.get("reason", "")),
        "risk_flags": json.dumps(score.get("risk_flags", []), ensure_ascii=False),
        "confidence": float(score.get("confidence", 0.0)),
        "rubric_version": str(score.get("rubric_version", "v1")),
        "model_provider": str(score.get("model_provider", "unknown")),
        "model_name": str(score.get("model_name", "unknown")),
        "prompt_version": str(score.get("prompt_version", "rss-score-v05")),
        "input_content_hash": score.get("input_content_hash"),
        "scoring_status": str(score.get("scoring_status", "success")),
        "error": score.get("error"),
        "is_active": is_active,
        "scored_at": datetime.now(UTC).isoformat(),
    }


def _insert_score_sql(dialect_name: str) -> str:
    if dialect_name == "postgresql":
        dimension_scores = "CAST(:dimension_scores AS jsonb)"
        dimension_reasons = "CAST(:dimension_reasons AS jsonb)"
        tags = "CAST(:tags AS jsonb)"
        risk_flags = "CAST(:risk_flags AS jsonb)"
    else:
        dimension_scores = ":dimension_scores"
        dimension_reasons = ":dimension_reasons"
        tags = ":tags"
        risk_flags = ":risk_flags"

    return f"""
        INSERT INTO article_base_scores (
            article_id, batch_id, base_score, recommendation_tier,
            summary_zh, summary_original, source_language,
            dimension_scores, dimension_reasons, tags, reason, risk_flags,
            confidence, rubric_version, model_provider, model_name,
            prompt_version, input_content_hash, scoring_status, error,
            is_active, scored_at
        )
        VALUES (
            :article_id, :batch_id, :base_score, :recommendation_tier,
            :summary_zh, :summary_original, :source_language,
            {dimension_scores}, {dimension_reasons}, {tags}, :reason, {risk_flags},
            :confidence, :rubric_version, :model_provider, :model_name,
            :prompt_version, :input_content_hash, :scoring_status, :error,
            :is_active, :scored_at
        )
        RETURNING id;
        """


def _dedupe_key_for(job_type: str, value: object) -> str:
    return hashlib.sha256(f"{job_type}:{value}".encode("utf-8")).hexdigest()

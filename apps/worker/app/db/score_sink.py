from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy import Engine, create_engine, text


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

    def enqueue_recommendations(self, _batch_id: object) -> None:
        return None

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
        "prompt_version": str(score.get("prompt_version", "rss-score-v04")),
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

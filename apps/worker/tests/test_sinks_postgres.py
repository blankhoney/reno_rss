from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.db.article_sink import DatabaseArticleSink
from app.db.recommendation_sink import DatabaseRecommendationSink
from app.db.score_sink import DatabaseScoreSink
from app.main import normalize_database_url


REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"


def test_postgres_scoring_and_recommendation_sinks_use_real_schema_types():
    database_url = os.environ.get("WORKER_QUEUE_POSTGRES_TEST_URL")
    if not database_url:
        pytest.skip("set WORKER_QUEUE_POSTGRES_TEST_URL to run the real Postgres sink test")

    _run_api_command(database_url, "alembic", "upgrade", "head")

    normalized_url = normalize_database_url(database_url) or database_url
    engine = create_engine(normalized_url, pool_pre_ping=True)
    score_sink = DatabaseScoreSink(engine=engine)
    recommendation_sink = DatabaseRecommendationSink(engine=engine)
    ids = _seed_real_schema_fixture(engine)

    try:
        first_score_id = score_sink.save_score(
            ids["article_id"],
            _score(
                ids["batch_id"],
                base_score=82,
                tier="read",
                dimension_scores={"risk_uncertainty": 30},
                tags=["ai"],
                risk_flags=[],
                status="success",
            ),
        )
        second_score_id = score_sink.save_score(
            ids["article_id"],
            _score(
                ids["batch_id"],
                base_score=91,
                tier="must_read",
                dimension_scores={"risk_uncertainty": 12},
                tags=["ai", "agent"],
                risk_flags=["low_signal"],
                status="success",
            ),
        )
        error_score_id = score_sink.save_score(
            ids["error_article_id"],
            _score(
                ids["batch_id"],
                base_score=8,
                tier="skip",
                dimension_scores={},
                tags=[],
                risk_flags=[],
                status="error",
                error="provider timeout",
            ),
        )

        with engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT id, article_id, is_active, scoring_status, dimension_scores,
                               dimension_reasons, tags, risk_flags
                        FROM article_base_scores
                        WHERE article_id IN (:article_id, :error_article_id)
                        ORDER BY id;
                        """
                    ),
                    {
                        "article_id": ids["article_id"],
                        "error_article_id": ids["error_article_id"],
                    },
                )
                .mappings()
                .all()
            )
            batch_items = (
                connection.execute(
                    text(
                        """
                        SELECT article_id, status, base_score_id, error
                        FROM scoring_batch_items
                        WHERE batch_id = :batch_id
                        ORDER BY article_id;
                        """
                    ),
                    {"batch_id": ids["batch_id"]},
                )
                .mappings()
                .all()
            )

        assert first_score_id != second_score_id
        assert error_score_id is not None
        article_rows = [row for row in rows if row["article_id"] == ids["article_id"]]
        assert [row["is_active"] for row in article_rows] == [False, True]
        assert article_rows[-1]["dimension_scores"] == {"risk_uncertainty": 12}
        assert article_rows[-1]["dimension_reasons"] == {"risk_uncertainty": "ok"}
        assert article_rows[-1]["tags"] == ["ai", "agent"]
        assert article_rows[-1]["risk_flags"] == ["low_signal"]

        error_row = [row for row in rows if row["article_id"] == ids["error_article_id"]][0]
        assert error_row["scoring_status"] == "error"
        assert error_row["is_active"] is False
        assert error_row["dimension_scores"] == {}
        assert error_row["tags"] == []
        assert batch_items == [
            {
                "article_id": ids["article_id"],
                "status": "scored",
                "base_score_id": second_score_id,
                "error": None,
            },
            {
                "article_id": ids["error_article_id"],
                "status": "error",
                "base_score_id": error_score_id,
                "error": "provider timeout",
            },
        ]

        assert recommendation_sink._user_priorities(ids["user_id"]) == {ids["feed_id"]: 7}
        candidate_rows = [
            row
            for row in recommendation_sink._candidate_rows()
            if row["article_id"] == ids["article_id"]
        ]
        assert candidate_rows == [
            {
                "article_id": ids["article_id"],
                "feed_ids": [ids["feed_id"]],
                "base_score": 91,
                "published_at": datetime(2026, 6, 24, 12, tzinfo=UTC),
                "risk_uncertainty": 12,
                "risk_flags": ["low_signal"],
            }
        ]

        score_sink.enqueue_recommendations(ids["batch_id"])
        score_sink.enqueue_recommendations(ids["batch_id"])
        with engine.begin() as connection:
            recommendation_jobs = (
                connection.execute(
                    text(
                        """
                        SELECT job_type, status, payload, created_by
                        FROM jobs
                        WHERE job_type='generate_recommendations'
                          AND payload @> CAST(:payload AS jsonb)
                        ORDER BY id;
                        """
                    ),
                    {"payload": json.dumps({"source_batch_id": ids["batch_id"]})},
                )
                .mappings()
                .all()
            )

        assert recommendation_jobs == [
            {
                "job_type": "generate_recommendations",
                "status": "queued",
                "payload": {"source_batch_id": ids["batch_id"]},
                "created_by": None,
            }
        ]
    finally:
        score_sink.dispose()
        recommendation_sink.dispose()


def test_postgres_article_sink_creates_miniflux_feed_before_fk_writes():
    database_url = os.environ.get("WORKER_QUEUE_POSTGRES_TEST_URL")
    if not database_url:
        pytest.skip("set WORKER_QUEUE_POSTGRES_TEST_URL to run the real Postgres sink test")

    _run_api_command(database_url, "alembic", "upgrade", "head")

    normalized_url = normalize_database_url(database_url) or database_url
    engine = create_engine(normalized_url, pool_pre_ping=True)
    sink = DatabaseArticleSink(engine=engine)
    base_id = uuid4().int % 1_000_000_000 + 2_000_000
    remote_feed_id = base_id
    feed_url = f"https://example.com/miniflux/{base_id}.xml"

    try:
        local_feed_id = sink.upsert_feed(
            {
                "feed_id": remote_feed_id,
                "feed_url": feed_url,
                "feed_title": "Miniflux Feed",
                "feed_site_url": f"https://example.com/miniflux/{base_id}",
            }
        )
        article_id = sink.upsert_article(
            {
                "primary_feed_id": local_feed_id,
                "title": "Miniflux article",
                "url": f"https://example.com/miniflux/{base_id}/article",
                "canonical_url": f"https://example.com/miniflux/{base_id}/article",
            }
        )
        sink.upsert_article_source(
            {
                "article_id": article_id,
                "feed_id": local_feed_id,
                "miniflux_entry_id": base_id + 1,
                "miniflux_category_id": 9,
                "source_url": f"https://example.com/miniflux/{base_id}/article",
                "source_title": "Miniflux article",
            }
        )

        with engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT f.id AS feed_id, f.miniflux_feed_id, f.feed_url,
                               a.primary_feed_id, s.feed_id AS source_feed_id,
                               s.miniflux_category_id
                        FROM feeds f
                        JOIN articles a ON a.primary_feed_id = f.id
                        JOIN article_sources s ON s.article_id = a.id
                        WHERE a.id = :article_id;
                        """
                    ),
                    {"article_id": article_id},
                )
                .mappings()
                .one()
            )

        assert row["feed_id"] == local_feed_id
        assert row["miniflux_feed_id"] == remote_feed_id
        assert row["feed_url"] == feed_url
        assert row["primary_feed_id"] == local_feed_id
        assert row["source_feed_id"] == local_feed_id
        assert row["miniflux_category_id"] == 9
    finally:
        sink.dispose()


def _seed_real_schema_fixture(engine):
    base_id = uuid4().int % 1_000_000_000 + 1_000_000
    user_id = str(uuid4())
    ids = {
        "user_id": user_id,
        "feed_id": base_id,
        "article_id": base_id + 1,
        "error_article_id": base_id + 2,
        "batch_id": base_id + 3,
        "source_id": base_id + 4,
        "error_source_id": base_id + 5,
        "item_id": base_id + 6,
        "error_item_id": base_id + 7,
    }
    now = datetime(2026, 6, 24, 12, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO app_users (
                    id, display_name, session_token_hash, recovery_code_hash, role
                )
                VALUES (
                    :user_id, 'Sink Test', :session_hash, :recovery_hash, 'user'
                );
                """
            ),
            {
                "user_id": user_id,
                "session_hash": f"session-{base_id}",
                "recovery_hash": f"recovery-{base_id}",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO feeds (id, feed_url, title, status)
                VALUES (:feed_id, :feed_url, 'Sink Feed', 'active');
                """
            ),
            {"feed_id": ids["feed_id"], "feed_url": f"https://example.com/{base_id}.xml"},
        )
        connection.execute(
            text(
                """
                INSERT INTO user_feed_subscriptions (
                    user_id, feed_id, enabled, user_priority
                )
                VALUES (:user_id, :feed_id, TRUE, 7);
                """
            ),
            {"user_id": user_id, "feed_id": ids["feed_id"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO articles (id, primary_feed_id, title, url, published_at, content_hash)
                VALUES
                    (:article_id, :feed_id, 'Scored article', :url, :published_at, 'hash-a'),
                    (:error_article_id, :feed_id, 'Error article', :error_url, :published_at, 'hash-b');
                """
            ),
            {
                "article_id": ids["article_id"],
                "error_article_id": ids["error_article_id"],
                "feed_id": ids["feed_id"],
                "url": f"https://example.com/articles/{base_id}",
                "error_url": f"https://example.com/articles/{base_id}-error",
                "published_at": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO article_sources (
                    id, article_id, feed_id, miniflux_entry_id, published_at
                )
                VALUES
                    (:source_id, :article_id, :feed_id, :entry_id, :published_at),
                    (:error_source_id, :error_article_id, :feed_id, :error_entry_id, :published_at);
                """
            ),
            {
                "source_id": ids["source_id"],
                "error_source_id": ids["error_source_id"],
                "article_id": ids["article_id"],
                "error_article_id": ids["error_article_id"],
                "feed_id": ids["feed_id"],
                "entry_id": base_id,
                "error_entry_id": base_id + 1,
                "published_at": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO scoring_batches (
                    id, name, status, trigger_type, candidate_window, article_count
                )
                VALUES (:batch_id, 'sink test', 'running', 'manual', 'custom', 2);
                """
            ),
            {"batch_id": ids["batch_id"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO scoring_batch_items (id, batch_id, article_id, status)
                VALUES
                    (:item_id, :batch_id, :article_id, 'pending'),
                    (:error_item_id, :batch_id, :error_article_id, 'pending');
                """
            ),
            {
                "item_id": ids["item_id"],
                "error_item_id": ids["error_item_id"],
                "batch_id": ids["batch_id"],
                "article_id": ids["article_id"],
                "error_article_id": ids["error_article_id"],
            },
        )
    return ids


def _score(
    batch_id: int,
    *,
    base_score: int,
    tier: str,
    dimension_scores: dict[str, int],
    tags: list[str],
    risk_flags: list[str],
    status: str,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "batch_id": batch_id,
        "base_score": base_score,
        "recommendation_tier": tier,
        "dimension_scores": dimension_scores,
        "dimension_reasons": {key: "ok" for key in dimension_scores},
        "summary_zh": "摘要" if status == "success" else "",
        "summary_original": "summary" if status == "success" else "",
        "source_language": "zh" if status == "success" else "unknown",
        "tags": tags,
        "reason": "useful" if status == "success" else "评分失败，需重新评分。",
        "risk_flags": risk_flags,
        "confidence": 0.8 if status == "success" else 0.0,
        "scoring_status": status,
        "error": error,
        "model_provider": "mock" if status == "success" else "baseline",
        "model_name": "mock" if status == "success" else "length-baseline",
        "prompt_version": "rss-score-v05",
    }


def _run_api_command(database_url: str, *command: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SCORING_DATABASE_URL"] = database_url
    return subprocess.run(
        ["uv", "run", "--isolated", "--with-editable", ".", "--extra", "dev", *command],
        cwd=API_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

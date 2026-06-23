"""Initial AI Reader v0.4 schema."""

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


CATEGORY_ROWS = [
    {"slug": "ai_infra", "name": "AI Infra", "sort_order": 10},
    {"slug": "agent", "name": "Agent", "sort_order": 20},
    {"slug": "rag", "name": "RAG", "sort_order": 30},
    {"slug": "paper", "name": "论文学术", "sort_order": 40},
    {"slug": "programming", "name": "编程", "sort_order": 50},
    {"slug": "tooling", "name": "工具软件版本", "sort_order": 60},
    {"slug": "product", "name": "产品", "sort_order": 70},
    {"slug": "business", "name": "商业", "sort_order": 80},
    {"slug": "game", "name": "游戏", "sort_order": 90},
    {"slug": "other", "name": "其他", "sort_order": 100},
]

RUBRIC_V1 = {
    "dimensions": [
        "topic_relevance",
        "information_density",
        "source_quality",
        "novelty",
        "timeliness",
        "actionability",
        "reading_cost_fit",
        "risk_uncertainty",
    ],
    "tiers": {
        "must_read": [85, 100],
        "read": [70, 84],
        "skim": [50, 69],
        "skip": [0, 49],
    },
    "ranking": {
        "algorithm_version": "b4.v1",
        "candidate_window_days": 3,
        "fallback_window_days": 14,
        "feed_priority_min": -20,
        "feed_priority_max": 20,
        "feedback_score_weight": 0.2,
        "feedback_adjustment_min": -20,
        "feedback_adjustment_max": 12,
        "feedback_adjustments": {
            "underrated": 8,
            "overrated": -10,
            "too_promotional": -12,
            "low_density": -12,
            "outdated": -12,
            "duplicate": -12,
            "wrong_category": -12,
            "other": 0,
        },
        "freshness_adjustments": {
            "within_24h": 3,
            "within_72h": 1,
            "older_than_7d": -4,
        },
        "subscription_slots": 8,
        "exploration": {
            "slots": 2,
            "min_base_score": 80,
            "max_risk_uncertainty": 50,
        },
        "tie_breakers": ["rank_score DESC", "published_at DESC", "article_id DESC"],
    },
    "prompt_version": "rss-score-v4",
}


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"))


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "app_users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("recovery_code_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'user'")),
        sa.Column(
            "session_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW() + interval '30 days'"),
        ),
        sa.Column("recovery_rotated_at", sa.DateTime(timezone=True)),
        _created_at(),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_app_users_role"),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0")),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column(
            "value",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        _updated_at(),
    )

    op.create_table(
        "feeds",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("feed_url", sa.Text(), nullable=False, unique=True),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("miniflux_feed_id", sa.BigInteger(), unique=True),
        sa.Column("title", sa.Text()),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("categories.id")),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'")),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id")),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("status IN ('active', 'paused', 'error')", name="ck_feeds_status"),
    )

    op.create_table(
        "scoring_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("candidate_window", sa.Text(), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id")),
        _created_at(),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'error')",
            name="ck_scoring_batches_status",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('manual', 'scheduled')",
            name="ck_scoring_batches_trigger_type",
        ),
        sa.CheckConstraint(
            "candidate_window IN ('today', 'last_3_days', 'custom')",
            name="ck_scoring_batches_candidate_window",
        ),
    )

    op.create_table(
        "rubric_versions",
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column(
            "definition",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _created_at(),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id")),
    )

    op.create_table(
        "articles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("primary_feed_id", sa.BigInteger(), sa.ForeignKey("feeds.id")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("author", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("content_text", sa.Text()),
        sa.Column("content_html", sa.Text()),
        sa.Column("content_source", sa.Text()),
        sa.Column("content_quality", sa.Text()),
        sa.Column("content_hash", sa.Text()),
        sa.Column("dedup_key", sa.Text()),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("content_expires_at", sa.DateTime(timezone=True)),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            "content_source IN ('miniflux_feed', 'readability', 'external', 'snippet_only')",
            name="ck_articles_content_source",
        ),
        sa.CheckConstraint(
            "content_quality IN ('full', 'partial', 'snippet')",
            name="ck_articles_content_quality",
        ),
    )

    op.create_table(
        "user_feed_subscriptions",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            nullable=False,
        ),
        sa.Column("feed_id", sa.BigInteger(), sa.ForeignKey("feeds.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("user_priority", sa.Integer(), server_default=sa.text("0")),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("user_id", "feed_id"),
        sa.CheckConstraint(
            "user_priority BETWEEN -20 AND 20",
            name="ck_user_feed_subscriptions_priority",
        ),
    )

    op.create_table(
        "article_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("feed_id", sa.BigInteger(), sa.ForeignKey("feeds.id"), nullable=False),
        sa.Column("miniflux_entry_id", sa.BigInteger(), nullable=False),
        sa.Column("miniflux_category_id", sa.BigInteger()),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_title", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("feed_id", "miniflux_entry_id", name="uq_article_sources_feed_entry"),
        sa.UniqueConstraint(
            "article_id",
            "feed_id",
            "miniflux_entry_id",
            name="uq_article_sources_article_feed_entry",
        ),
    )

    op.create_table(
        "user_article_states",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            nullable=False,
        ),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'unread'")),
        sa.Column("saved", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("read_progress", sa.Numeric(4, 3)),
        _updated_at(),
        sa.PrimaryKeyConstraint("user_id", "article_id"),
        sa.CheckConstraint(
            "status IN ('unread', 'read', 'skipped')",
            name="ck_user_article_states_status",
        ),
        sa.CheckConstraint(
            "read_progress IS NULL OR (read_progress >= 0 AND read_progress <= 1)",
            name="ck_user_article_states_progress",
        ),
    )

    op.create_table(
        "recommendation_editions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            nullable=False,
        ),
        sa.Column("source_batch_id", sa.BigInteger(), sa.ForeignKey("scoring_batches.id")),
        sa.Column("edition_type", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "edition_type IN ('homepage_top10')",
            name="ck_recommendation_editions_type",
        ),
    )

    op.create_table(
        "rubric_change_proposals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "proposed_patch",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("rubric_version_before", sa.Text(), sa.ForeignKey("rubric_versions.version")),
        sa.Column("rubric_version_after", sa.Text(), sa.ForeignKey("rubric_versions.version")),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        _created_at(),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_rubric_change_proposals_status",
        ),
    )

    op.create_table(
        "rescore_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            nullable=False,
        ),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        _created_at(),
        sa.CheckConstraint(
            "requested_count > 0 AND requested_count <= 10",
            name="ck_rescore_requests_count",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'done', 'error')",
            name="ck_rescore_requests_status",
        ),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0")),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column(
            "progress",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "result",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("5")),
        sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id")),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_jobs_status",
        ),
    )

    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("suite", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column(
            "params",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("artifact_path", sa.Text()),
        sa.Column(
            "cost_estimate",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id")),
        _created_at(),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "suite IN ('ranking', 'model_swap', 'db_perf')",
            name="ck_benchmark_runs_suite",
        ),
        sa.CheckConstraint(
            "mode IN ('ci_mini', 'manual_full')",
            name="ck_benchmark_runs_mode",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_benchmark_runs_status",
        ),
    )

    op.create_table(
        "article_base_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), sa.ForeignKey("scoring_batches.id")),
        sa.Column("base_score", sa.Integer()),
        sa.Column("recommendation_tier", sa.Text()),
        sa.Column("summary_zh", sa.Text()),
        sa.Column("summary_original", sa.Text()),
        sa.Column("source_language", sa.Text()),
        sa.Column(
            "dimension_scores",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "dimension_reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "risk_flags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column(
            "rubric_version",
            sa.Text(),
            sa.ForeignKey("rubric_versions.version"),
            nullable=False,
        ),
        sa.Column("model_provider", sa.Text()),
        sa.Column("model_name", sa.Text()),
        sa.Column("prompt_version", sa.Text()),
        sa.Column("input_content_hash", sa.Text()),
        sa.Column("scoring_status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scored_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "base_score IS NULL OR (base_score >= 0 AND base_score <= 100)",
            name="ck_scores_base_score",
        ),
        sa.CheckConstraint(
            "recommendation_tier IS NULL OR "
            "recommendation_tier IN ('must_read', 'read', 'skim', 'skip')",
            name="ck_scores_recommendation_tier",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_scores_confidence",
        ),
        sa.CheckConstraint("scoring_status IN ('success', 'error')", name="ck_scores_status"),
    )

    op.create_table(
        "scoring_batch_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("batch_id", sa.BigInteger(), sa.ForeignKey("scoring_batches.id"), nullable=False),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("base_score_id", sa.BigInteger(), sa.ForeignKey("article_base_scores.id")),
        sa.Column("error", sa.Text()),
        sa.UniqueConstraint("batch_id", "article_id", name="uq_scoring_batch_items_batch_article"),
        sa.CheckConstraint(
            "status IN ('pending', 'scored', 'error')",
            name="ck_scoring_batch_items_status",
        ),
    )

    op.create_table(
        "user_article_feedback_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            nullable=False,
        ),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("user_score", sa.Integer(), nullable=False),
        sa.Column("feedback_type", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("user_id", "article_id", name="uq_feedback_user_article"),
        sa.CheckConstraint("user_score >= 0 AND user_score <= 100", name="ck_feedback_user_score"),
    )

    op.create_table(
        "article_annotations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("selected_text", sa.Text()),
        sa.Column("content", sa.Text(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id")),
        sa.Column("delete_reason", sa.Text()),
        sa.CheckConstraint(
            "type IN ('annotation', 'comment', 'review')",
            name="ck_annotations_type",
        ),
    )

    op.create_table(
        "user_memories",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            nullable=False,
        ),
        sa.Column("memory_type", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_memories_confidence",
        ),
        sa.CheckConstraint("status IN ('active', 'deleted')", name="ck_memories_status"),
    )

    op.create_table(
        "recommendation_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "edition_id",
            sa.BigInteger(),
            sa.ForeignKey("recommendation_editions.id"),
            nullable=False,
        ),
        sa.Column("article_id", sa.BigInteger(), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("rank_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False),
        sa.UniqueConstraint("edition_id", "rank", name="uq_recommendation_items_edition_rank"),
        sa.CheckConstraint(
            "source IN ('subscription', 'exploration')",
            name="ck_recommendation_items_source",
        ),
    )

    _create_indexes()
    _seed_initial_data()


def _create_indexes() -> None:
    op.create_index(
        "ix_articles_primary_feed_published",
        "articles",
        ["primary_feed_id", sa.text("published_at DESC")],
    )
    op.create_index("ix_articles_published_id", "articles", [sa.text("published_at DESC"), sa.text("id DESC")])
    op.create_index(
        "uq_articles_dedup_key",
        "articles",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text("dedup_key IS NOT NULL"),
    )
    op.create_index("ix_articles_content_quality", "articles", ["content_quality"])
    op.create_index("ix_article_sources_article", "article_sources", ["article_id"])
    op.create_index(
        "ix_article_sources_feed_published",
        "article_sources",
        ["feed_id", sa.text("published_at DESC")],
    )
    op.create_index(
        "ix_user_article_states_status",
        "user_article_states",
        ["user_id", "status", "article_id"],
    )
    op.create_index(
        "ix_user_article_states_saved",
        "user_article_states",
        ["user_id", "saved", "article_id"],
    )
    op.create_index("ix_user_article_states_article", "user_article_states", ["article_id"])
    op.create_index(
        "uq_article_base_scores_active_article",
        "article_base_scores",
        ["article_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "ix_article_base_scores_active_score",
        "article_base_scores",
        [sa.text("base_score DESC"), "article_id"],
        postgresql_where=sa.text("scoring_status = 'success' AND is_active = true"),
    )
    op.create_index("ix_article_base_scores_rubric", "article_base_scores", ["rubric_version"])
    op.create_index("ix_article_base_scores_batch", "article_base_scores", ["batch_id"])
    op.create_index("ix_feedback_article", "user_article_feedback_scores", ["article_id"])
    op.create_index(
        "ix_feedback_user_created",
        "user_article_feedback_scores",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_annotations_article_visible",
        "article_annotations",
        ["article_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_annotations_user", "article_annotations", ["user_id"])
    op.create_index(
        "ix_recommendation_editions_user_generated",
        "recommendation_editions",
        ["user_id", sa.text("generated_at DESC")],
    )
    op.create_index("ix_recommendation_items_article", "recommendation_items", ["article_id"])
    op.create_index(
        "ix_user_feed_subscriptions_enabled",
        "user_feed_subscriptions",
        ["user_id", "enabled"],
    )
    op.create_index("ix_user_feed_subscriptions_feed", "user_feed_subscriptions", ["feed_id"])
    op.create_index(
        "ix_jobs_queued_priority",
        "jobs",
        [sa.text("priority DESC"), "id"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "uq_jobs_running_dedupe",
        "jobs",
        ["job_type", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_benchmark_runs_suite_created",
        "benchmark_runs",
        ["suite", sa.text("created_at DESC")],
    )
    op.create_index("ix_benchmark_runs_status", "benchmark_runs", ["status"])


def _seed_initial_data() -> None:
    category_table = sa.table(
        "categories",
        sa.column("slug", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("sort_order", sa.Integer()),
    )
    op.bulk_insert(category_table, CATEGORY_ROWS)
    op.execute(
        sa.text(
            "INSERT INTO rubric_versions (version, definition, active) "
            "VALUES ('v1', CAST(:definition AS JSONB), true)"
        ).bindparams(definition=json.dumps(RUBRIC_V1))
    )


def downgrade() -> None:
    for table_name in (
        "recommendation_items",
        "user_memories",
        "article_annotations",
        "user_article_feedback_scores",
        "scoring_batch_items",
        "article_base_scores",
        "benchmark_runs",
        "jobs",
        "rescore_requests",
        "rubric_change_proposals",
        "recommendation_editions",
        "user_article_states",
        "article_sources",
        "user_feed_subscriptions",
        "articles",
        "rubric_versions",
        "scoring_batches",
        "feeds",
        "app_settings",
        "categories",
        "app_users",
    ):
        op.drop_table(table_name)

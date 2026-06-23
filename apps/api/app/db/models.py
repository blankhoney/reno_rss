from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


metadata = MetaData()


def created_at_column() -> Column[DateTime]:
    return Column("created_at", DateTime(timezone=True), server_default=text("NOW()"))


def updated_at_column() -> Column[DateTime]:
    return Column("updated_at", DateTime(timezone=True), server_default=text("NOW()"))


app_users = Table(
    "app_users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("display_name", Text, nullable=False),
    Column("session_token_hash", Text, nullable=False, unique=True),
    Column("recovery_code_hash", Text, nullable=False, unique=True),
    Column("role", Text, nullable=False, server_default=text("'user'")),
    Column(
        "session_expires_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW() + interval '30 days'"),
    ),
    Column("recovery_rotated_at", DateTime(timezone=True)),
    created_at_column(),
    Column("last_seen_at", DateTime(timezone=True)),
    CheckConstraint("role IN ('user', 'admin')", name="ck_app_users_role"),
)

categories = Table(
    "categories",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("slug", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("sort_order", Integer, server_default=text("0")),
)

feeds = Table(
    "feeds",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("feed_url", Text, nullable=False, unique=True),
    Column("canonical_url", Text),
    Column("miniflux_feed_id", BigInteger, unique=True),
    Column("title", Text),
    Column("category_id", BigInteger, ForeignKey("categories.id")),
    Column("status", Text, server_default=text("'active'")),
    Column("added_by_user_id", UUID(as_uuid=True), ForeignKey("app_users.id")),
    created_at_column(),
    updated_at_column(),
    CheckConstraint("status IN ('active', 'paused', 'error')", name="ck_feeds_status"),
)

user_feed_subscriptions = Table(
    "user_feed_subscriptions",
    metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), primary_key=True),
    Column("feed_id", BigInteger, ForeignKey("feeds.id"), primary_key=True),
    Column("enabled", Boolean, server_default=text("true")),
    Column("user_priority", Integer, server_default=text("0")),
    created_at_column(),
    updated_at_column(),
    CheckConstraint(
        "user_priority BETWEEN -20 AND 20",
        name="ck_user_feed_subscriptions_priority",
    ),
)

articles = Table(
    "articles",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("primary_feed_id", BigInteger, ForeignKey("feeds.id")),
    Column("title", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("canonical_url", Text),
    Column("author", Text),
    Column("published_at", DateTime(timezone=True)),
    Column("content_text", Text),
    Column("content_html", Text),
    Column("content_source", Text),
    Column("content_quality", Text),
    Column("content_hash", Text),
    Column("dedup_key", Text),
    Column("fetched_at", DateTime(timezone=True)),
    Column("content_expires_at", DateTime(timezone=True)),
    created_at_column(),
    updated_at_column(),
    CheckConstraint(
        "content_source IN ('miniflux_feed', 'readability', 'external', 'snippet_only')",
        name="ck_articles_content_source",
    ),
    CheckConstraint(
        "content_quality IN ('full', 'partial', 'snippet')",
        name="ck_articles_content_quality",
    ),
)

article_sources = Table(
    "article_sources",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("article_id", BigInteger, ForeignKey("articles.id"), nullable=False),
    Column("feed_id", BigInteger, ForeignKey("feeds.id"), nullable=False),
    Column("miniflux_entry_id", BigInteger, nullable=False),
    Column("miniflux_category_id", BigInteger),
    Column("source_url", Text),
    Column("source_title", Text),
    Column("published_at", DateTime(timezone=True)),
    Column("first_seen_at", DateTime(timezone=True), server_default=text("NOW()")),
    Column("last_seen_at", DateTime(timezone=True), server_default=text("NOW()")),
    UniqueConstraint("feed_id", "miniflux_entry_id", name="uq_article_sources_feed_entry"),
    UniqueConstraint(
        "article_id",
        "feed_id",
        "miniflux_entry_id",
        name="uq_article_sources_article_feed_entry",
    ),
)

user_article_states = Table(
    "user_article_states",
    metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), primary_key=True),
    Column("article_id", BigInteger, ForeignKey("articles.id"), primary_key=True),
    Column("status", Text, nullable=False, server_default=text("'unread'")),
    Column("saved", Boolean, server_default=text("false")),
    Column("read_progress", Numeric(4, 3)),
    updated_at_column(),
    CheckConstraint("status IN ('unread', 'read', 'skipped')", name="ck_user_article_states_status"),
    CheckConstraint(
        "read_progress IS NULL OR (read_progress >= 0 AND read_progress <= 1)",
        name="ck_user_article_states_progress",
    ),
)

scoring_batches = Table(
    "scoring_batches",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text),
    Column("status", Text, nullable=False, server_default=text("'queued'")),
    Column("trigger_type", Text, nullable=False),
    Column("candidate_window", Text, nullable=False),
    Column("article_count", Integer, nullable=False, server_default=text("0")),
    Column("created_by", UUID(as_uuid=True), ForeignKey("app_users.id")),
    created_at_column(),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    CheckConstraint("status IN ('queued', 'running', 'done', 'error')", name="ck_scoring_batches_status"),
    CheckConstraint(
        "trigger_type IN ('manual', 'scheduled')",
        name="ck_scoring_batches_trigger_type",
    ),
    CheckConstraint(
        "candidate_window IN ('today', 'last_3_days', 'custom')",
        name="ck_scoring_batches_candidate_window",
    ),
)

rubric_versions = Table(
    "rubric_versions",
    metadata,
    Column("version", Text, primary_key=True),
    Column("definition", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("active", Boolean, nullable=False, server_default=text("false")),
    created_at_column(),
    Column("created_by", UUID(as_uuid=True), ForeignKey("app_users.id")),
)

article_base_scores = Table(
    "article_base_scores",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("article_id", BigInteger, ForeignKey("articles.id"), nullable=False),
    Column("batch_id", BigInteger, ForeignKey("scoring_batches.id")),
    Column("base_score", Integer),
    Column("recommendation_tier", Text),
    Column("summary_zh", Text),
    Column("summary_original", Text),
    Column("source_language", Text),
    Column("dimension_scores", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("dimension_reasons", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("tags", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("reason", Text),
    Column("risk_flags", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("confidence", Numeric(4, 3)),
    Column("rubric_version", Text, ForeignKey("rubric_versions.version"), nullable=False),
    Column("model_provider", Text),
    Column("model_name", Text),
    Column("prompt_version", Text),
    Column("input_content_hash", Text),
    Column("scoring_status", Text, nullable=False),
    Column("error", Text),
    Column("is_active", Boolean, nullable=False, server_default=text("false")),
    Column("scored_at", DateTime(timezone=True)),
    CheckConstraint("base_score IS NULL OR (base_score >= 0 AND base_score <= 100)", name="ck_scores_base_score"),
    CheckConstraint(
        "recommendation_tier IS NULL OR recommendation_tier IN ('must_read', 'read', 'skim', 'skip')",
        name="ck_scores_recommendation_tier",
    ),
    CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_scores_confidence"),
    CheckConstraint("scoring_status IN ('success', 'error')", name="ck_scores_status"),
)

scoring_batch_items = Table(
    "scoring_batch_items",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("batch_id", BigInteger, ForeignKey("scoring_batches.id"), nullable=False),
    Column("article_id", BigInteger, ForeignKey("articles.id"), nullable=False),
    Column("status", Text, nullable=False, server_default=text("'pending'")),
    Column("base_score_id", BigInteger, ForeignKey("article_base_scores.id")),
    Column("error", Text),
    UniqueConstraint("batch_id", "article_id", name="uq_scoring_batch_items_batch_article"),
    CheckConstraint("status IN ('pending', 'scored', 'error')", name="ck_scoring_batch_items_status"),
)

user_article_feedback_scores = Table(
    "user_article_feedback_scores",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False),
    Column("article_id", BigInteger, ForeignKey("articles.id"), nullable=False),
    Column("user_score", Integer, nullable=False),
    Column("feedback_type", Text, nullable=False),
    Column("reason", Text, nullable=False),
    created_at_column(),
    updated_at_column(),
    UniqueConstraint("user_id", "article_id", name="uq_feedback_user_article"),
    CheckConstraint("user_score >= 0 AND user_score <= 100", name="ck_feedback_user_score"),
)

article_annotations = Table(
    "article_annotations",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("article_id", BigInteger, ForeignKey("articles.id"), nullable=False),
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False),
    Column("type", Text, nullable=False),
    Column("selected_text", Text),
    Column("content", Text, nullable=False),
    created_at_column(),
    updated_at_column(),
    Column("deleted_at", DateTime(timezone=True)),
    Column("deleted_by", UUID(as_uuid=True), ForeignKey("app_users.id")),
    Column("delete_reason", Text),
    CheckConstraint("type IN ('annotation', 'comment', 'review')", name="ck_annotations_type"),
)

user_memories = Table(
    "user_memories",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False),
    Column("memory_type", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("confidence", Numeric(4, 3)),
    Column("source", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'active'")),
    created_at_column(),
    updated_at_column(),
    CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_memories_confidence"),
    CheckConstraint("status IN ('active', 'deleted')", name="ck_memories_status"),
)

recommendation_editions = Table(
    "recommendation_editions",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False),
    Column("source_batch_id", BigInteger, ForeignKey("scoring_batches.id")),
    Column("edition_type", Text, nullable=False),
    Column("algorithm_version", Text, nullable=False),
    Column("generated_at", DateTime(timezone=True), server_default=text("NOW()")),
    CheckConstraint("edition_type IN ('homepage_top10')", name="ck_recommendation_editions_type"),
)

recommendation_items = Table(
    "recommendation_items",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("edition_id", BigInteger, ForeignKey("recommendation_editions.id"), nullable=False),
    Column("article_id", BigInteger, ForeignKey("articles.id"), nullable=False),
    Column("rank", Integer, nullable=False),
    Column("rank_score", Numeric(6, 2), nullable=False),
    Column("tier", Text, nullable=False),
    Column("reason", Text),
    Column("source", Text, nullable=False),
    UniqueConstraint("edition_id", "rank", name="uq_recommendation_items_edition_rank"),
    CheckConstraint("source IN ('subscription', 'exploration')", name="ck_recommendation_items_source"),
)

rubric_change_proposals = Table(
    "rubric_change_proposals",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("source", Text, nullable=False),
    Column("proposed_patch", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("evidence_json", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("status", Text, nullable=False, server_default=text("'pending'")),
    Column("rubric_version_before", Text, ForeignKey("rubric_versions.version")),
    Column("rubric_version_after", Text, ForeignKey("rubric_versions.version")),
    Column("reviewed_by", UUID(as_uuid=True), ForeignKey("app_users.id")),
    Column("reviewed_at", DateTime(timezone=True)),
    created_at_column(),
    CheckConstraint(
        "status IN ('pending', 'approved', 'rejected')",
        name="ck_rubric_change_proposals_status",
    ),
)

rescore_requests = Table(
    "rescore_requests",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), nullable=False),
    Column("requested_count", Integer, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'queued'")),
    created_at_column(),
    CheckConstraint("requested_count > 0 AND requested_count <= 10", name="ck_rescore_requests_count"),
    CheckConstraint("status IN ('queued', 'done', 'error')", name="ck_rescore_requests_status"),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("job_type", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'queued'")),
    Column("priority", Integer, server_default=text("0")),
    Column("payload", JSONB, nullable=False),
    Column("dedupe_key", Text, nullable=False),
    Column("progress", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("result", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("locked_by", Text),
    Column("locked_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, server_default=text("0")),
    Column("max_attempts", Integer, server_default=text("5")),
    Column("run_after", DateTime(timezone=True), server_default=text("NOW()")),
    Column("completed_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("created_by", UUID(as_uuid=True), ForeignKey("app_users.id")),
    created_at_column(),
    updated_at_column(),
    CheckConstraint(
        "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
        name="ck_jobs_status",
    ),
)

job_watchers = Table(
    "job_watchers",
    metadata,
    Column("job_id", BigInteger, ForeignKey("jobs.id"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("app_users.id"), primary_key=True),
    created_at_column(),
)

benchmark_runs = Table(
    "benchmark_runs",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("suite", Text, nullable=False),
    Column("mode", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'queued'")),
    Column("params", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("metrics", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("artifact_path", Text),
    Column("cost_estimate", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("created_by", UUID(as_uuid=True), ForeignKey("app_users.id")),
    created_at_column(),
    Column("completed_at", DateTime(timezone=True)),
    CheckConstraint("suite IN ('ranking', 'model_swap', 'db_perf')", name="ck_benchmark_runs_suite"),
    CheckConstraint("mode IN ('ci_mini', 'manual_full')", name="ck_benchmark_runs_mode"),
    CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_benchmark_runs_status"),
)

app_settings = Table(
    "app_settings",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    updated_at_column(),
)


Index("ix_articles_primary_feed_published", articles.c.primary_feed_id, articles.c.published_at.desc())
Index("ix_articles_published_id", articles.c.published_at.desc(), articles.c.id.desc())
Index(
    "uq_articles_dedup_key",
    articles.c.dedup_key,
    unique=True,
    postgresql_where=articles.c.dedup_key.is_not(None),
)
Index("ix_articles_content_quality", articles.c.content_quality)
Index("ix_article_sources_article", article_sources.c.article_id)
Index("ix_article_sources_feed_published", article_sources.c.feed_id, article_sources.c.published_at.desc())
Index(
    "ix_user_article_states_status",
    user_article_states.c.user_id,
    user_article_states.c.status,
    user_article_states.c.article_id,
)
Index(
    "ix_user_article_states_saved",
    user_article_states.c.user_id,
    user_article_states.c.saved,
    user_article_states.c.article_id,
)
Index("ix_user_article_states_article", user_article_states.c.article_id)
Index(
    "uq_article_base_scores_active_article",
    article_base_scores.c.article_id,
    unique=True,
    postgresql_where=article_base_scores.c.is_active.is_(True),
)
Index(
    "ix_article_base_scores_active_score",
    article_base_scores.c.base_score.desc(),
    article_base_scores.c.article_id,
    postgresql_where=text("scoring_status = 'success' AND is_active = true"),
)
Index("ix_article_base_scores_rubric", article_base_scores.c.rubric_version)
Index("ix_article_base_scores_batch", article_base_scores.c.batch_id)
Index("ix_feedback_article", user_article_feedback_scores.c.article_id)
Index("ix_feedback_user_created", user_article_feedback_scores.c.user_id, user_article_feedback_scores.c.created_at)
Index(
    "ix_annotations_article_visible",
    article_annotations.c.article_id,
    postgresql_where=article_annotations.c.deleted_at.is_(None),
)
Index("ix_annotations_user", article_annotations.c.user_id)
Index(
    "ix_recommendation_editions_user_generated",
    recommendation_editions.c.user_id,
    recommendation_editions.c.generated_at.desc(),
)
Index("ix_recommendation_items_article", recommendation_items.c.article_id)
Index("ix_user_feed_subscriptions_enabled", user_feed_subscriptions.c.user_id, user_feed_subscriptions.c.enabled)
Index("ix_user_feed_subscriptions_feed", user_feed_subscriptions.c.feed_id)
Index(
    "ix_jobs_queued_priority",
    jobs.c.priority.desc(),
    jobs.c.id,
    postgresql_where=jobs.c.status == "queued",
)
Index(
    "uq_jobs_running_dedupe",
    jobs.c.job_type,
    jobs.c.dedupe_key,
    unique=True,
    postgresql_where=jobs.c.status.in_(("queued", "running")),
)
Index("ix_job_watchers_user", job_watchers.c.user_id, job_watchers.c.job_id)
Index("ix_benchmark_runs_suite_created", benchmark_runs.c.suite, benchmark_runs.c.created_at.desc())
Index("ix_benchmark_runs_status", benchmark_runs.c.status)

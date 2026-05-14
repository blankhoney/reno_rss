-- Scoring database schema (idempotent — safe to re-run)
-- All tables use IF NOT EXISTS; upserts use ON CONFLICT.

CREATE TABLE IF NOT EXISTS items_snapshot (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          TEXT        NOT NULL,
    miniflux_entry_id  BIGINT      NOT NULL,
    feed_id            BIGINT,
    title              TEXT,
    url                TEXT,
    published_at       TIMESTAMPTZ,
    content_hash       TEXT        NOT NULL,
    fetched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, miniflux_entry_id)
);

CREATE TABLE IF NOT EXISTS item_scores (
    id                 BIGSERIAL   PRIMARY KEY,
    tenant_id          TEXT        NOT NULL,
    miniflux_entry_id  BIGINT      NOT NULL,
    content_hash       TEXT        NOT NULL,
    score              INT         NOT NULL,
    dimension_scores   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    tags               JSONB       NOT NULL,
    reason             TEXT        NOT NULL,
    summary_zh         TEXT        NOT NULL DEFAULT '',
    summary_original   TEXT        NOT NULL DEFAULT '',
    source_language    TEXT        NOT NULL DEFAULT 'unknown',
    dimension_reasons  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    model_version      TEXT        NOT NULL,
    model_provider     TEXT        NOT NULL DEFAULT 'baseline',
    model_name         TEXT        NOT NULL DEFAULT 'length-baseline',
    prompt_version     TEXT        NOT NULL DEFAULT 'none',
    confidence         NUMERIC(4,3),
    scoring_status     TEXT        NOT NULL DEFAULT 'success',
    error_message      TEXT,
    scored_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, miniflux_entry_id, content_hash, model_version)
);

ALTER TABLE item_scores
    ADD COLUMN IF NOT EXISTS dimension_scores JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE item_scores
    ADD COLUMN IF NOT EXISTS summary_zh TEXT NOT NULL DEFAULT '';

ALTER TABLE item_scores
    ADD COLUMN IF NOT EXISTS summary_original TEXT NOT NULL DEFAULT '';

ALTER TABLE item_scores
    ADD COLUMN IF NOT EXISTS source_language TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE item_scores
    ADD COLUMN IF NOT EXISTS dimension_reasons JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Tracks batch scoring job runs for audit / idempotency
CREATE TABLE IF NOT EXISTS scoring_jobs (
    id          BIGSERIAL   PRIMARY KEY,
    tenant_id   TEXT        NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status      TEXT        NOT NULL DEFAULT 'running',
    entries_processed INT,
    error_message TEXT
);

-- Digest batches generated from high-scoring items in one worker cycle.
CREATE TABLE IF NOT EXISTS digests (
    id             BIGSERIAL   PRIMARY KEY,
    tenant_id      TEXT        NOT NULL,
    window_start   TIMESTAMPTZ NOT NULL,
    window_end     TIMESTAMPTZ NOT NULL,
    title          TEXT        NOT NULL,
    summary        TEXT        NOT NULL,
    model_provider TEXT        NOT NULL,
    model_name     TEXT        NOT NULL,
    model_version  TEXT        NOT NULL,
    prompt_version TEXT        NOT NULL,
    status         TEXT        NOT NULL DEFAULT 'success',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, window_start, window_end, prompt_version)
);

-- Items selected for a digest. The unique key prevents duplicate rows
-- when a worker restarts and rebuilds the same digest window.
CREATE TABLE IF NOT EXISTS digest_items (
    id                BIGSERIAL PRIMARY KEY,
    digest_id         BIGINT    NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
    tenant_id         TEXT      NOT NULL,
    miniflux_entry_id BIGINT    NOT NULL,
    rank              INT       NOT NULL,
    score             INT       NOT NULL,
    title             TEXT,
    url               TEXT,
    reason            TEXT,
    UNIQUE (digest_id, tenant_id, miniflux_entry_id),
    UNIQUE (digest_id, rank)
);

-- Cursor for incremental export (e.g. to downstream analytics)
CREATE TABLE IF NOT EXISTS export_cursor (
    tenant_id       TEXT        PRIMARY KEY,
    last_score_id   BIGINT      NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Per-feed health tracking
CREATE TABLE IF NOT EXISTS feed_health (
    tenant_id       TEXT        NOT NULL,
    feed_id         BIGINT      NOT NULL,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    entry_count     INT         NOT NULL DEFAULT 0,
    error_message   TEXT,
    PRIMARY KEY (tenant_id, feed_id)
);

CREATE TABLE IF NOT EXISTS reader_entry_states (
    tenant_id          TEXT        NOT NULL,
    miniflux_user_id   BIGINT      NOT NULL,
    miniflux_entry_id  BIGINT      NOT NULL,
    read_later         BOOLEAN     NOT NULL DEFAULT FALSE,
    last_read_at       TIMESTAMPTZ,
    archived_at        TIMESTAMPTZ,
    notes              TEXT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, miniflux_user_id, miniflux_entry_id)
);

CREATE TABLE IF NOT EXISTS scoring_settings (
    tenant_id               TEXT        PRIMARY KEY,
    auto_score_new_unread   BOOLEAN     NOT NULL DEFAULT TRUE,
    webhook_max_entries     INT         NOT NULL DEFAULT 20,
    manual_batch_size       INT         NOT NULL DEFAULT 20,
    manual_rescore_enabled  BOOLEAN     NOT NULL DEFAULT TRUE,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE scoring_settings
    ADD COLUMN IF NOT EXISTS manual_batch_size INT NOT NULL DEFAULT 20;

CREATE TABLE IF NOT EXISTS entry_project_queue (
    id                 BIGSERIAL   PRIMARY KEY,
    tenant_id          TEXT        NOT NULL,
    miniflux_entry_id  BIGINT      NOT NULL,
    title              TEXT        NOT NULL,
    url                TEXT        NOT NULL,
    score              INT,
    status             TEXT        NOT NULL DEFAULT 'queued',
    source             TEXT        NOT NULL DEFAULT 'manual',
    queued_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, miniflux_entry_id)
);

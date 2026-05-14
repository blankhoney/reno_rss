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
    manual_rescore_enabled  BOOLEAN     NOT NULL DEFAULT TRUE,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

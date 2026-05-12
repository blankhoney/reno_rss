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

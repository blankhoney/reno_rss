"""Unique index for scheduler time-bucket dedupe keys (any status)."""

from alembic import op


revision = "0004_jobs_sched_dedupe_key"
down_revision = "0003_user_article_state_project"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Scheduler keys must not re-fire after a short job succeeds in the same
    # bucket; the active-only unique index on (job_type, dedupe_key) is not enough.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_sched_dedupe_key
        ON jobs (dedupe_key)
        WHERE dedupe_key LIKE 'sched:%'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_jobs_sched_dedupe_key")

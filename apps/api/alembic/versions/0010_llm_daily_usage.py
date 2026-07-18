"""Durable score / ask / agent daily usage counters."""

from alembic import op
import sqlalchemy as sa


revision = "0010_llm_daily_usage"
down_revision = "0009_project_acl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_daily_usage",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("account", sa.Text(), primary_key=True),
        sa.Column("used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "account IN ('score', 'ask', 'agent')",
            name="ck_llm_daily_usage_account",
        ),
        sa.CheckConstraint("used >= 0", name="ck_llm_daily_usage_used"),
    )


def downgrade() -> None:
    op.drop_table("llm_daily_usage")

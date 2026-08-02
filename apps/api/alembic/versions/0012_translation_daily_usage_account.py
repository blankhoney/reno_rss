"""Add a separate daily usage account for article translation."""

from alembic import op


revision = "0012_translation_daily_usage_account"
down_revision = "0011_project_requires_saved"
branch_labels = None
depends_on = None


_USAGE_ACCOUNT_CONSTRAINT = "ck_llm_daily_usage_account"


def _replace_account_constraint(expression: str) -> None:
    op.drop_constraint(_USAGE_ACCOUNT_CONSTRAINT, "llm_daily_usage", type_="check")
    op.create_check_constraint(
        _USAGE_ACCOUNT_CONSTRAINT,
        "llm_daily_usage",
        expression,
    )


def upgrade() -> None:
    _replace_account_constraint("account IN ('score', 'ask', 'agent', 'translate')")


def downgrade() -> None:
    _replace_account_constraint("account IN ('score', 'ask', 'agent')")

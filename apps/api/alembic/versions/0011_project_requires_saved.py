"""Require project article states to remain saved."""

from alembic import op


revision = "0011_project_requires_saved"
down_revision = "0010_llm_daily_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM user_article_states
            WHERE project IS TRUE AND saved IS NOT TRUE
          ) THEN
            RAISE EXCEPTION
              'cannot add project/saved invariant: existing invalid user_article_states rows require manual repair';
          END IF;
        END $$;
        """
    )
    op.create_check_constraint(
        "ck_user_article_states_project_requires_saved",
        "user_article_states",
        "NOT project OR saved IS TRUE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_article_states_project_requires_saved",
        "user_article_states",
        type_="check",
    )

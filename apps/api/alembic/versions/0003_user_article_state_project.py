"""Add project state to user article states."""

from alembic import op
import sqlalchemy as sa


revision = "0003_user_article_state_project"
down_revision = "0002_article_translation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_article_states",
        sa.Column("project", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "ix_user_article_states_project",
        "user_article_states",
        ["user_id", "project", "article_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_article_states_project", table_name="user_article_states")
    op.drop_column("user_article_states", "project")

"""user saved searches JSON store

Revision ID: 0007_user_saved_searches
Revises: 0006_user_reader_rules
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_user_saved_searches"
down_revision = "0006_user_reader_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_saved_searches",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_users.id"), primary_key=True),
        sa.Column(
            "items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("user_saved_searches")

"""Per-user interest reset timestamp for durable personalization resets."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_user_interest_reset"
down_revision = "0007_user_saved_searches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_interest_resets",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_interest_resets")

"""Per-user reader rules JSON store (boost/mute/keyword/threshold)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_user_reader_rules"
down_revision = "0005_annotation_spaced_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_reader_rules",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_reader_rules")

"""Shared project ACL grants (GOAL §4.E multi-user capability)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_project_acl"
down_revision = "0008_user_interest_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_acl_grants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="ck_project_acl_role",
        ),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_acl_user"),
    )
    op.create_index("ix_project_acl_project", "project_acl_grants", ["project_id"])
    op.create_index("ix_project_acl_user", "project_acl_grants", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_project_acl_user", table_name="project_acl_grants")
    op.drop_index("ix_project_acl_project", table_name="project_acl_grants")
    op.drop_table("project_acl_grants")

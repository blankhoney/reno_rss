"""Add spaced-review fields to article_annotations."""

from alembic import op
import sqlalchemy as sa


revision = "0005_annotation_spaced_review"
down_revision = "0004_jobs_sched_dedupe_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "article_annotations",
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "article_annotations",
        sa.Column(
            "interval_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "article_annotations",
        sa.Column(
            "review_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # Existing highlights become immediately due (same as created_at).
    op.execute(
        """
        UPDATE article_annotations
        SET next_review_at = created_at
        WHERE next_review_at IS NULL
        """
    )
    op.create_index(
        "ix_annotations_user_next_review",
        "article_annotations",
        ["user_id", "next_review_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_annotations_user_next_review", table_name="article_annotations")
    op.drop_column("article_annotations", "review_count")
    op.drop_column("article_annotations", "interval_days")
    op.drop_column("article_annotations", "next_review_at")

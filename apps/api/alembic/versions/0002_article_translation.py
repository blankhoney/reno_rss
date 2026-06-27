"""Add on-demand article translation cache."""

from alembic import op
import sqlalchemy as sa


revision = "0002_article_translation"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("content_zh", sa.Text()))
    op.add_column("articles", sa.Column("content_zh_status", sa.Text()))
    op.add_column("articles", sa.Column("translated_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_articles_content_zh_status",
        "articles",
        "content_zh_status IS NULL OR content_zh_status IN ('queued', 'running', 'succeeded', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_articles_content_zh_status", "articles", type_="check")
    op.drop_column("articles", "translated_at")
    op.drop_column("articles", "content_zh_status")
    op.drop_column("articles", "content_zh")

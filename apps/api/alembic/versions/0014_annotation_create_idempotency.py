"""Add permanent owner-scoped annotation create operation bindings."""

from alembic import op
import sqlalchemy as sa


revision = "0014_annotation_idempotency"
down_revision = "0013_annotation_search_keys"
branch_labels = None
depends_on = None


_INDEX_NAME = "uq_annotations_user_create_idempotency_key"
_PAIRED_NULL_CHECK = "ck_annotations_create_idempotency_pair"
_FINGERPRINT_CHECK = "ck_annotations_create_request_fingerprint"


def upgrade() -> None:
    op.add_column(
        "article_annotations",
        sa.Column("create_idempotency_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_annotations",
        sa.Column("create_request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        _PAIRED_NULL_CHECK,
        "article_annotations",
        "(create_idempotency_key IS NULL) = (create_request_fingerprint IS NULL)",
    )
    op.create_check_constraint(
        _FINGERPRINT_CHECK,
        "article_annotations",
        "create_request_fingerprint IS NULL OR create_request_fingerprint ~ '^[0-9a-f]{64}$'",
    )
    op.create_index(
        _INDEX_NAME,
        "article_annotations",
        ["user_id", "create_idempotency_key"],
        unique=True,
        postgresql_where=sa.text("create_idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="article_annotations")
    op.drop_constraint(_FINGERPRINT_CHECK, "article_annotations", type_="check")
    op.drop_constraint(_PAIRED_NULL_CHECK, "article_annotations", type_="check")
    op.drop_column("article_annotations", "create_request_fingerprint")
    op.drop_column("article_annotations", "create_idempotency_key")

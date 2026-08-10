"""Add nullable annotation search keys and invalidate them on source writes."""

from alembic import op
import sqlalchemy as sa


revision = "0013_annotation_search_keys"
down_revision = "0012_translation_usage"
branch_labels = None
depends_on = None


_TRIGGER_NAME = "trg_annotations_invalidate_search_keys"
_FUNCTION_NAME = "invalidate_annotation_search_keys"


def upgrade() -> None:
    op.add_column(
        "article_annotations",
        sa.Column("searchable_body", sa.Text(), nullable=True),
    )
    op.add_column(
        "article_annotations",
        sa.Column("searchable_selected_text", sa.Text(), nullable=True),
    )
    op.execute(
        f"""
        CREATE FUNCTION {_FUNCTION_NAME}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.searchable_body := NULL;
            NEW.searchable_selected_text := NULL;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_NAME}
        BEFORE INSERT OR UPDATE OF content, selected_text
        ON article_annotations
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON article_annotations")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}()")
    op.drop_column("article_annotations", "searchable_selected_text")
    op.drop_column("article_annotations", "searchable_body")

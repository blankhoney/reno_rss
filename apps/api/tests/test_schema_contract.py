import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory


EXPECTED_TABLES = {
    "app_users",
    "categories",
    "feeds",
    "user_feed_subscriptions",
    "articles",
    "article_sources",
    "user_article_states",
    "article_base_scores",
    "user_article_feedback_scores",
    "article_annotations",
    "user_memories",
    "scoring_batches",
    "scoring_batch_items",
    "recommendation_editions",
    "recommendation_items",
    "rubric_versions",
    "rubric_change_proposals",
    "rescore_requests",
    "jobs",
    "job_watchers",
    "benchmark_runs",
    "app_settings",
    "user_reader_rules",
    "user_saved_searches",
    "user_interest_resets",
    "project_acl_grants",
    "llm_daily_usage",
}


class MigrationOpRecorder:
    def __init__(self):
        self.tables = {}
        self.statements = []

    def execute(self, statement, *_args, **_kwargs):
        self.statements.append(str(statement))

    def bulk_insert(self, *_args, **_kwargs):
        return None

    def create_index(self, *_args, **_kwargs):
        return None

    def create_check_constraint(self, *_args, **_kwargs):
        return None

    def drop_constraint(self, *_args, **_kwargs):
        return None

    def add_column(self, table_name, column):
        self.tables[table_name][column.name] = column

    def create_table(self, name, *elements, **_kwargs):
        self.tables[name] = {
            element.name: element for element in elements if isinstance(element, sa.Column)
        }


def load_migration(filename: str):
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".", "_"), migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def load_initial_migration():
    return load_migration("0001_initial.py")


def migration_scripts():
    api_root = Path(__file__).parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    assert len(heads) == 1, f"expected exactly one Alembic head, found {heads}"
    return list(reversed(list(scripts.walk_revisions(base="base", head=heads[0]))))


def test_alembic_revision_ids_fit_version_table_column():
    versions = Path(__file__).parents[1] / "alembic" / "versions"

    oversized = []
    for migration_path in sorted(versions.glob("*.py")):
        migration = load_migration(migration_path.name)
        revision = str(migration.revision)
        if len(revision) > 32:
            oversized.append(f"{migration_path.name}: {revision}")

    assert oversized == []


def test_ci_snapshot_restore_checks_current_migration_head():
    ci_workflow = (Path(__file__).parents[3] / ".github/workflows/ci.yml").read_text()

    assert "ScriptDirectory.from_config" in ci_workflow
    assert "get_heads()" in ci_workflow
    assert 'len(heads) != 1' in ci_workflow
    assert 'grep -qx "$MIGRATION_HEAD"' in ci_workflow
    assert '"migration": os.environ["MIGRATION_HEAD"]' in ci_workflow
    assert "0012_translation_usage" not in ci_workflow


def test_initial_migration_defines_required_tables():
    from app.db.models import metadata

    assert EXPECTED_TABLES.issubset(set(metadata.tables))


def test_user_session_expiry_defaults_to_30_days():
    from app.db.models import metadata

    session_expires_at = metadata.tables["app_users"].columns["session_expires_at"]

    assert session_expires_at.nullable is False
    assert session_expires_at.server_default is not None
    assert "30 days" in str(session_expires_at.server_default.arg)


def test_article_source_preserves_feed_entry_provenance():
    from app.db.models import metadata

    article_sources = metadata.tables["article_sources"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in article_sources.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("feed_id", "miniflux_entry_id") in unique_columns
    assert ("article_id", "feed_id", "miniflux_entry_id") in unique_columns


def test_score_history_uses_active_score_not_article_rubric_unique_key():
    from app.db.models import metadata

    scores = metadata.tables["article_base_scores"]
    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in scores.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    unique_indexes = {
        tuple(column.name for column in index.columns)
        for index in scores.indexes
        if index.unique
    }

    assert ("article_id", "rubric_version") not in unique_constraints
    assert ("article_id",) in unique_indexes


def test_recommendation_items_store_rank_score_not_ai_base_score():
    from app.db.models import metadata

    recommendation_items = metadata.tables["recommendation_items"]

    assert "rank_score" in recommendation_items.columns
    assert "score" not in recommendation_items.columns


def test_jobs_require_dedupe_key_with_unique_queued_running_index():
    from app.db.models import metadata

    jobs = metadata.tables["jobs"]
    unique_indexes = {
        tuple(column.name for column in index.columns)
        for index in jobs.indexes
        if index.unique
    }

    assert jobs.columns["dedupe_key"].nullable is False
    assert ("job_type", "dedupe_key") in unique_indexes


def test_initial_migration_bootstraps_extension_and_seed_data():
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "0001_initial.py"

    source = migration_path.read_text()

    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in source
    assert "metadata.create_all" not in source
    assert "metadata.drop_all" not in source
    assert "op.create_table" in source
    assert "categories" in source
    assert "rubric_versions" in source
    assert "def upgrade()" in source
    assert "def downgrade()" in source


def test_migration_column_nullability_matches_model():
    from app.db.models import metadata

    recorder = MigrationOpRecorder()
    for migration in migration_scripts():
        migration.module.op = recorder

        migration.module.upgrade()

    mismatches = []
    for table_name, model_table in metadata.tables.items():
        migration_columns = recorder.tables[table_name]
        for model_column in model_table.columns:
            migration_column = migration_columns[model_column.name]
            if migration_column.nullable != model_column.nullable:
                mismatches.append(
                    f"{table_name}.{model_column.name}: "
                    f"model nullable={model_column.nullable}, "
                    f"migration nullable={migration_column.nullable}"
                )

    assert mismatches == []


def test_annotation_search_key_expand_is_nullable_and_invalidates_source_writes():
    recorder = MigrationOpRecorder()
    for migration in migration_scripts():
        migration.module.op = recorder
        migration.module.upgrade()

    annotations = recorder.tables["article_annotations"]
    assert annotations["searchable_body"].nullable is True
    assert annotations["searchable_selected_text"].nullable is True

    ddl = "\n".join(recorder.statements)
    assert "CREATE FUNCTION invalidate_annotation_search_keys()" in ddl
    assert "NEW.searchable_body := NULL" in ddl
    assert "NEW.searchable_selected_text := NULL" in ddl
    assert "BEFORE INSERT OR UPDATE OF content, selected_text" in ddl
    assert "ON article_annotations" in ddl

    migration_source = (
        Path(__file__).parents[1]
        / "alembic/versions/0013_annotation_searchable_body.py"
    ).read_text()
    assert "DROP TRIGGER IF EXISTS" in migration_source
    assert "DROP FUNCTION IF EXISTS" in migration_source
    assert 'op.drop_column("article_annotations", "searchable_selected_text")' in migration_source
    assert 'op.drop_column("article_annotations", "searchable_body")' in migration_source


def test_rubric_seed_contains_b4_ranking_parameters():
    migration = load_initial_migration()

    ranking = migration.RUBRIC_V1["ranking"]

    assert ranking["algorithm_version"] == "b4.v1"
    assert ranking["candidate_window_days"] == 3
    assert ranking["fallback_window_days"] == 14
    assert ranking["feedback_adjustments"]["underrated"] == 8
    assert ranking["feedback_adjustments"]["duplicate"] == -12
    assert ranking["freshness_adjustments"]["within_24h"] == 3
    assert ranking["exploration"]["slots"] == 2
    assert ranking["exploration"]["min_base_score"] == 80
    assert ranking["exploration"]["max_risk_uncertainty"] == 50

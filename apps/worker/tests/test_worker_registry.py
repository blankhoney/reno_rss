from app.main import build_handler_registry


EXPECTED_JOB_TYPES = {
    "fetch_article_content",
    "generate_recommendations",
    "score_batch",
    "sync_miniflux_entries",
    "translate_article",
    "worker_echo",
}


def test_worker_registry_matches_expected_job_types():
    registry = build_handler_registry()

    assert set(registry) == EXPECTED_JOB_TYPES
    assert all(callable(handler) for handler in registry.values())

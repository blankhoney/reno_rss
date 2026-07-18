from app.main import build_handler_registry


EXPECTED_JOB_TYPES = {
    "auto_score_candidates",
    "fetch_article_content",
    "generate_daily_brief",
    "generate_recommendations",
    "research_brief",
    "run_benchmark",
    "score_batch",
    "sync_miniflux_entries",
    "translate_article",
    "worker_echo",
}


def test_worker_registry_matches_expected_job_types():
    registry = build_handler_registry()

    assert set(registry) == EXPECTED_JOB_TYPES
    assert all(callable(handler) for handler in registry.values())

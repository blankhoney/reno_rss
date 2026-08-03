from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_worker_image_copies_ranking_rule_dependencies():
    dockerfile = (REPOSITORY_ROOT / "apps/worker/Dockerfile").read_text()

    assert "apps/api/app/domain/ranking.py" in dockerfile
    assert "apps/api/app/domain/rules.py" in dockerfile


def test_translation_budget_reaches_api_and_worker_services():
    compose = (REPOSITORY_ROOT / "infra/compose/docker-compose.base.yml").read_text()

    assert compose.count("TRANSLATION_DAILY_CALL_BUDGET:") == 2


def test_translation_budget_is_documented_in_example_environment():
    example_environment = (REPOSITORY_ROOT / ".env.example").read_text()

    assert "TRANSLATION_DAILY_CALL_BUDGET=60" in example_environment

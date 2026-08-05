"""Static regression locks for the GitHub Actions CI delivery boundary."""

from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/ci.yml"


def _workflow_source() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def _job_block(source: str, job_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        source,
    )
    assert match is not None, f"missing CI job {job_name!r}"
    return match.group("body")


def _job_condition(source: str, job_name: str) -> str:
    match = re.search(r"(?m)^    if: (?P<condition>[^\n]+)$", _job_block(source, job_name))
    assert match is not None, f"missing if condition for CI job {job_name!r}"
    return match.group("condition")


def _paths_ignore_entries(source: str, event_name: str) -> list[str]:
    event_match = re.search(
        rf"(?ms)^  {re.escape(event_name)}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:\n|^\npermissions:)",
        source,
    )
    assert event_match is not None, f"missing {event_name} trigger"
    paths_match = re.search(
        r"(?ms)^    paths-ignore:\n(?P<entries>(?:^      - [^\n]+\n)+)",
        event_match.group("body"),
    )
    assert paths_match is not None, f"missing {event_name}.paths-ignore"
    return [line.removeprefix("      - ").rstrip() for line in paths_match.group("entries").splitlines()]


def test_pr_runs_checks_only_and_main_is_the_only_publish_deploy_boundary():
    source = _workflow_source()

    assert _job_condition(source, "images") == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    )
    assert _job_condition(source, "deploy-staging") == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    )
    assert "github.event.pull_request.head.repo.full_name == github.repository" not in (
        _job_block(source, "images") + _job_block(source, "deploy-staging")
    )


def test_ci_concurrency_cancels_only_superseded_pr_runs():
    source = _workflow_source()
    concurrency_match = re.search(r"(?ms)^concurrency:\n(?P<body>.*?)(?=^jobs:\n)", source)

    assert concurrency_match is not None, "missing workflow-level concurrency"
    concurrency = concurrency_match.group("body")
    assert "  group: ci-${{ github.event.pull_request.number || github.ref }}\n" in concurrency
    assert "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n" in concurrency


def test_ci_ignores_only_root_plans_and_docs_for_prs_and_main_pushes():
    source = _workflow_source()

    assert _paths_ignore_entries(source, "pull_request") == ["PLANS.md", "docs/**"]
    assert _paths_ignore_entries(source, "push") == ["PLANS.md", "docs/**"]
    assert "**/*.md" not in source

"""Static regression locks for the GitHub Actions CI delivery boundary."""

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/ci.yml"
REMOTE_DEPLOY_SCRIPT = REPOSITORY_ROOT / ".github/scripts/remote-deploy.sh"
VALIDATE_DEPLOY_ENV_SCRIPT = REPOSITORY_ROOT / ".github/scripts/validate-deploy-env.sh"


def _load_workflow(path: Path) -> dict[str, Any]:
    """Parse workflow YAML without treating comments or shell text as structure."""
    parser = subprocess.run(
        [
            "ruby",
            "-ryaml",
            "-rjson",
            "-e",
            (
                "document = YAML.load_file(ARGV.fetch(0)); "
                "document['on'] = document.delete(true) if document.key?(true); "
                "puts JSON.generate(document)"
            ),
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(parser.stdout)
    assert isinstance(document, dict)
    return document


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o700)


def _remote_deploy_harness(
    tmp_path: Path,
    *,
    deploy_ref: str = "main",
    deploy_sha: str = "a" * 40,
    fetched_sha: str | None = None,
    docker_exit: int = 0,
    chmod_exit: int = 0,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, list[str]]:
    case_dir = tmp_path / f"remote-{docker_exit}-{chmod_exit}"
    case_dir.mkdir()
    fake_bin = case_dir / "bin"
    fake_bin.mkdir()
    docker_log = case_dir / "docker-log"
    gate_log = case_dir / "gate-log"
    mktemp_log = case_dir / "mktemp-log"
    app_dir = case_dir / "app"
    (app_dir / ".git").mkdir(parents=True)
    (app_dir / "infra/scripts").mkdir(parents=True)
    _write_executable(
        app_dir / "infra/scripts/deploy.sh",
        "#!/usr/bin/env bash\nprintf '%s\\n' deploy >> \"$GATE_LOG\"\nexit 0\n",
    )
    _write_executable(
        app_dir / "infra/scripts/smoke-test.sh",
        "#!/usr/bin/env bash\nprintf '%s\\n' smoke >> \"$GATE_LOG\"\nexit 0\n",
    )

    real_mktemp = shutil.which("mktemp")
    real_chmod = shutil.which("chmod")
    assert real_mktemp is not None
    assert real_chmod is not None
    _write_executable(
        fake_bin / "mktemp",
        """#!/usr/bin/env bash
set -euo pipefail
path="$($REAL_MKTEMP \"$@\")"
printf '%s\\n' \"$path\" >> \"$MKTEMP_LOG\"
printf '%s\\n' \"$path\"
""",
    )
    _write_executable(
        fake_bin / "chmod",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ \"${FAKE_CHMOD_EXIT:-0}\" != 0 ]]; then
    exit \"$FAKE_CHMOD_EXIT\"
fi
exec \"$REAL_CHMOD\" \"$@\"
""",
    )
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
mode="$(python3 -c 'import os,sys; print(format(os.stat(sys.argv[1]).st_mode & 0o777, "03o"))' "$DOCKER_CONFIG")"
printf '%s\\n%s\\n' "$DOCKER_CONFIG" "$mode" > "$DOCKER_LOG"
cat >/dev/null
exit "${DOCKER_EXIT:-0}"
""",
    )
    _write_executable(
        fake_bin / "git",
        """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
    status|fetch|checkout|check-ref-format) exit 0 ;;
    rev-parse)
        [[ "${2:-}" == "FETCH_HEAD^{commit}" ]] || exit 1
        printf '%s\\n' "$FETCHED_SHA"
        ;;
    *) exit 1 ;;
esac
""",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "REAL_MKTEMP": real_mktemp,
            "REAL_CHMOD": real_chmod,
            "MKTEMP_LOG": str(mktemp_log),
            "DOCKER_LOG": str(docker_log),
            "DOCKER_EXIT": str(docker_exit),
            "FAKE_CHMOD_EXIT": str(chmod_exit),
            "DEPLOY_ENV": "staging",
            "DEPLOY_REF": deploy_ref,
            "DEPLOY_SHA": deploy_sha,
            "FETCHED_SHA": fetched_sha or deploy_sha,
            "GATE_LOG": str(gate_log),
            "IMAGE_REGISTRY": "ghcr.io/example/project",
            "IMAGE_TAG": "sha-test",
            "VPS_APP_DIR": str(app_dir),
            "GHCR_USERNAME": "ghcr-user",
            "GHCR_TOKEN_B64": base64.b64encode(b"test-ghcr-token").decode("ascii"),
        }
    )
    result = subprocess.run(
        ["bash", str(REMOTE_DEPLOY_SCRIPT)],
        cwd=REPOSITORY_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    config_paths = mktemp_log.read_text(encoding="utf-8").splitlines()
    return result, docker_log, gate_log, config_paths


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


def test_request_workflows_have_strict_dispatch_inputs_and_no_target_ref():
    for workflow_path in (
        REPOSITORY_ROOT / ".github/workflows/deploy-staging.yml",
        REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml",
        REPOSITORY_ROOT / ".github/workflows/rollback.yml",
    ):
        workflow = _load_workflow(workflow_path)
        dispatch = workflow["on"]["workflow_dispatch"]
        inputs = dispatch["inputs"]

        expected_inputs = {"image_tag", "deploy_sha"}
        if workflow_path.name == "rollback.yml":
            expected_inputs.add("env")
        assert set(inputs) == expected_inputs
        assert "git_ref" not in inputs
        for input_name in ("image_tag", "deploy_sha"):
            assert inputs[input_name]["required"] is True
            assert inputs[input_name]["type"] == "string"
        assert inputs["deploy_sha"]["description"]
        assert inputs["image_tag"]["description"]
        if workflow_path.name == "rollback.yml":
            assert inputs["env"]["type"] == "choice"
            assert inputs["env"]["options"] == ["staging", "prod"]


def test_request_workflows_emit_one_stable_data_schema():
    expected_fields = [
        "schema_version",
        "request_type",
        "environment",
        "image_tag",
        "deploy_sha",
    ]
    for workflow_path in (
        REPOSITORY_ROOT / ".github/workflows/deploy-staging.yml",
        REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml",
        REPOSITORY_ROOT / ".github/workflows/rollback.yml",
    ):
        workflow = _load_workflow(workflow_path)
        job = workflow["jobs"]["request"]
        steps = job["steps"]
        validation = steps[0]
        upload = steps[1]

        assert validation["name"] == "Validate request inputs"
        assert upload["uses"] == "actions/upload-artifact@v4"
        assert upload["with"]["if-no-files-found"] == "error"
        assert upload["with"]["retention-days"] == 7
        assert set(validation["env"]) == {"REQUEST_TYPE", "DEPLOY_ENV", "IMAGE_TAG", "DEPLOY_SHA"}
        assert validation["env"]["IMAGE_TAG"] == "${{ inputs.image_tag }}"
        assert validation["env"]["DEPLOY_SHA"] == "${{ inputs.deploy_sha }}"
        assert "trusted-deploy-request/v1" in validation["run"]
        assert "jq -n" in validation["run"]
        assert "environment: $environment" in validation["run"]
        assert "image_tag: $image_tag" in validation["run"]
        assert "deploy_sha: $deploy_sha" in validation["run"]

        if workflow_path.name == "rollback.yml":
            assert validation["env"]["REQUEST_TYPE"] == "rollback"
            assert validation["env"]["DEPLOY_ENV"] == "${{ inputs.env }}"
            assert upload["with"]["name"] == "trusted-rollback-request"
        else:
            assert validation["env"]["REQUEST_TYPE"] == "deploy"
            assert validation["env"]["DEPLOY_ENV"] == (
                "staging" if workflow_path.name == "deploy-staging.yml" else "prod"
            )
            assert upload["with"]["name"] == (
                "trusted-staging-deploy-request"
                if workflow_path.name == "deploy-staging.yml"
                else "trusted-production-deploy-request"
            )

        jq_object = validation["run"].split("'{", 1)[1].split("}' >", 1)[0]
        emitted_fields = re.findall(r"^    ([a-z_]+): \$[a-z_]+,?$", jq_object, re.MULTILINE)
        assert emitted_fields == expected_fields


def test_request_workflows_validate_inputs_without_shell_expression_injection():

    for workflow_path in (
        REPOSITORY_ROOT / ".github/workflows/deploy-staging.yml",
        REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml",
        REPOSITORY_ROOT / ".github/workflows/rollback.yml",
    ):
        workflow = _load_workflow(workflow_path)
        validation = workflow["jobs"]["request"]["steps"][0]
        run_block = validation["run"]
        assert "${{ inputs." not in run_block
        assert '[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]]' in run_block
        assert '[[ "$IMAGE_TAG" =~ ^sha-[0-9a-f]{7}$ ]]' in run_block
        assert '"$IMAGE_TAG" == "$expected_tag"' in run_block
        assert 'jq -n' in run_block
        assert '"$request_file"' in run_block


def test_request_workflows_have_no_privileged_steps_on_any_dispatch_ref():
    forbidden_actions = {"actions/checkout@v4"}
    forbidden_markers = (
        ".github/scripts/",
        "secrets.",
        "github.token",
        "docker login",
        "docker build",
        "docker push",
        "ssh ",
        "git fetch",
        "git checkout",
        "git rev-parse",
    )
    for workflow_path in (
        REPOSITORY_ROOT / ".github/workflows/deploy-staging.yml",
        REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml",
        REPOSITORY_ROOT / ".github/workflows/rollback.yml",
    ):
        workflow = _load_workflow(workflow_path)
        assert workflow.get("permissions") == {}
        assert "environment" not in workflow
        job = workflow["jobs"]["request"]
        assert "environment" not in job
        assert [step.get("uses") for step in job["steps"]] == [
            None,
            "actions/upload-artifact@v4",
        ]
        assert all(step.get("uses") not in forbidden_actions for step in job["steps"])
        source = workflow_path.read_text(encoding="utf-8")
        assert "packages: write" not in source
        assert "git_ref" not in source
        assert not any(marker in source for marker in forbidden_markers)
        for step in job["steps"]:
            if "run" in step:
                assert "${{ inputs." not in step["run"]


def test_request_artifacts_are_fixed_data_paths_not_input_paths():
    for workflow_path in (
        REPOSITORY_ROOT / ".github/workflows/deploy-staging.yml",
        REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml",
        REPOSITORY_ROOT / ".github/workflows/rollback.yml",
    ):
        workflow = _load_workflow(workflow_path)
        upload = workflow["jobs"]["request"]["steps"][1]["with"]
        assert "${{ inputs." not in upload["name"]
        assert "${{ inputs." not in upload["path"]
        assert upload["path"].endswith(".json")
        assert upload["name"].startswith("trusted-")


def test_request_jobs_do_not_gate_or_execute_target_branch_code():
    for workflow_path in (
        REPOSITORY_ROOT / ".github/workflows/deploy-staging.yml",
        REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml",
        REPOSITORY_ROOT / ".github/workflows/rollback.yml",
    ):
        workflow = _load_workflow(workflow_path)
        job = workflow["jobs"]["request"]
        assert "if" not in job
        assert "environment" not in job
        assert job["runs-on"] == "ubuntu-latest"
        assert [step["name"] for step in job["steps"]] == [
            "Validate request inputs",
            "Upload trusted deploy request"
            if workflow_path.name != "rollback.yml"
            else "Upload trusted rollback request",
        ]


def test_remote_deploy_decodes_stdin_token_and_clears_it():
    source = REMOTE_DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'GHCR_TOKEN_B64:?GHCR_TOKEN_B64 is required' in source
    assert 'base64 --decode | docker login ghcr.io' in source
    assert 'unset GHCR_TOKEN_B64' in source
    assert 'GHCR_TOKEN"' not in source
    assert 'docker_config_dir=""' in source
    assert 'docker_config_dir="$(mktemp -d)"' in source
    assert 'chmod 700 "$docker_config_dir"' in source
    assert 'export DOCKER_CONFIG="$docker_config_dir"' in source
    assert 'trap cleanup_docker_config EXIT' in source
    assert "trap 'exit 129' HUP" in source
    assert "trap 'exit 130' INT" in source
    assert "trap 'exit 143' TERM" in source
    assert 'trap - EXIT HUP INT TERM' in source
    assert 'case "$DEPLOY_REF" in' in source
    assert 'refs/tags/release-?*)' in source
    assert 'git check-ref-format "$DEPLOY_REF"' in source
    assert '[[ ! "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]]' in source
    assert 'fetched_sha="$(git rev-parse \'FETCH_HEAD^{commit}\')"' in source
    assert '[[ "$fetched_sha" != "$DEPLOY_SHA" ]]' in source
    assert source.index('[[ "$fetched_sha" != "$DEPLOY_SHA" ]]') < source.index('run_gate "deploy')


@pytest.mark.parametrize(
    ("docker_exit", "chmod_exit", "expected_returncode"),
    ((0, 0, 0), (23, 0, 23), (0, 23, 23)),
)
def test_remote_deploy_cleans_docker_config_on_success_and_failures(
    tmp_path, docker_exit, chmod_exit, expected_returncode
):
    result, docker_log, gate_log, config_paths = _remote_deploy_harness(
        tmp_path,
        docker_exit=docker_exit,
        chmod_exit=chmod_exit,
    )

    assert result.returncode == expected_returncode
    assert len(config_paths) == 1
    assert not Path(config_paths[0]).exists()
    if chmod_exit == 0:
        docker_log_lines = docker_log.read_text(encoding="utf-8").splitlines()
        assert docker_log_lines == [config_paths[0], "700"]
    else:
        assert not docker_log.exists()

    if docker_exit == 0 and chmod_exit == 0:
        assert gate_log.read_text(encoding="utf-8").splitlines() == ["deploy", "smoke"]
    else:
        assert not gate_log.exists()


def test_remote_deploy_accepts_only_main_or_release_tag(tmp_path):
    result, docker_log, gate_log, config_paths = _remote_deploy_harness(
        tmp_path,
        deploy_ref="refs/tags/release-2026.08.09",
    )

    assert result.returncode == 0
    assert docker_log.exists()
    assert gate_log.read_text(encoding="utf-8").splitlines() == ["deploy", "smoke"]
    assert all(not Path(path).exists() for path in config_paths)


@pytest.mark.parametrize("deploy_ref", ["feature/attacker", "main; touch /tmp/ci-contract-pwned"])
def test_remote_deploy_rejects_untrusted_ref_before_login(tmp_path, deploy_ref):
    result, docker_log, gate_log, config_paths = _remote_deploy_harness(
        tmp_path,
        deploy_ref=deploy_ref,
    )

    assert result.returncode != 0
    assert "must be main or refs/tags/release-*" in result.stdout
    assert not docker_log.exists()
    assert not gate_log.exists()
    assert all(not Path(path).exists() for path in config_paths)


def test_remote_deploy_rejects_fetch_sha_mismatch_before_deploy_gate(tmp_path):
    result, docker_log, gate_log, config_paths = _remote_deploy_harness(
        tmp_path,
        deploy_sha="a" * 40,
        fetched_sha="b" * 40,
    )

    assert result.returncode != 0
    assert "fetched commit does not match DEPLOY_SHA" in result.stdout
    assert docker_log.exists()
    assert not gate_log.exists()
    assert all(not Path(path).exists() for path in config_paths)


def test_deploy_validation_requires_known_hosts_secret():
    source = VALIDATE_DEPLOY_ENV_SCRIPT.read_text(encoding="utf-8")

    assert '"VPS_KNOWN_HOSTS:VPS_KNOWN_HOSTS"' in source

"""Static regression locks for the GitHub Actions CI delivery boundary."""

import base64
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
from typing import Any
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/ci.yml"
REMOTE_DEPLOY_SCRIPT = REPOSITORY_ROOT / ".github/scripts/remote-deploy.sh"
VALIDATE_DEPLOY_ENV_SCRIPT = REPOSITORY_ROOT / ".github/scripts/validate-deploy-env.sh"
MAIN_1_SHA = "1" * 40
MAIN_2_SHA = "2" * 40
FORK_SHA = "f" * 40
MISSING_SHA = "9" * 40


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
    deploy_sha: str = MAIN_2_SHA,
    main_tip: str = MAIN_2_SHA,
    shallow_repository: str = "false",
    dirty_output: str = "",
    merge_base_exit: int | None = None,
    fetch_exit: int = 0,
    fetch_creates_grafts: bool = False,
    docker_exit: int = 0,
    chmod_exit: int = 0,
    image_tag: str | None = None,
    grafts_content: str = "",
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path, list[str]]:
    case_dir = tmp_path / f"remote-{docker_exit}-{chmod_exit}-{fetch_exit}"
    case_dir.mkdir()
    fake_bin = case_dir / "bin"
    fake_bin.mkdir()
    docker_log = case_dir / "docker-log"
    gate_log = case_dir / "gate-log"
    git_log = case_dir / "git-log"
    mktemp_log = case_dir / "mktemp-log"
    app_dir = case_dir / "app"
    grafts_path = app_dir / ".git/info/grafts"
    grafts_path.parent.mkdir(parents=True)
    if grafts_content:
        grafts_path.write_text(grafts_content, encoding="utf-8")
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
if [[ -n "${GHCR_TOKEN_B64+x}" || -n "${ghcr_token_b64+x}" ]]; then
    exit 97
fi
mode="$(python3 -c 'import os,sys; print(format(os.stat(sys.argv[1]).st_mode & 0o777, "03o"))' "$DOCKER_CONFIG")"
token="$(cat)"
[[ "$token" == "$EXPECTED_DOCKER_TOKEN" ]] || exit 98
printf '%s\\n%s\\n' "$DOCKER_CONFIG" "$mode" > "$DOCKER_LOG"
printf '{"auths":{}}\\n' > "$DOCKER_CONFIG/config.json"
exit "${DOCKER_EXIT:-0}"
""",
    )
    _write_executable(
        fake_bin / "git",
        """#!/usr/bin/env bash
set -euo pipefail
token_state=absent
docker_auth_state=absent
if [[ -n "${GHCR_TOKEN_B64+x}" || -n "${ghcr_token_b64+x}" ]]; then
    token_state=present
fi
if [[ -e "$DOCKER_CONFIG/config.json" ]]; then
    docker_auth_state=present
fi
[[ "$token_state" == absent ]]
[[ "$docker_auth_state" == absent ]]
[[ "${GIT_NO_REPLACE_OBJECTS:-}" == 1 ]]
printf 'token=%s docker-auth=%s no-replace=%s | %s\\n' \
    "$token_state" "$docker_auth_state" "${GIT_NO_REPLACE_OBJECTS:-unset}" "$*" >> "$GIT_LOG"
if [[ "${1:-}" == "--no-replace-objects" ]]; then
    shift
fi
case "$1" in
    status)
        printf '%s' "$DIRTY_OUTPUT"
        ;;
    fetch)
        if [[ "$FETCH_EXIT" != 0 ]]; then
            exit "$FETCH_EXIT"
        fi
        if [[ "$FETCH_CREATES_GRAFTS" == 1 ]]; then
            printf '%s %s\\n' "$MAIN_TIP" "$FORK_SHA" > "$GRAFTS_PATH"
        fi
        ;;
    rev-parse)
        case "${2:-}" in
            --git-path)
                [[ "${3:-}" == "info/grafts" ]] || exit 1
                printf '%s\\n' "$GRAFTS_PATH"
                ;;
            --is-shallow-repository) printf '%s\\n' "$SHALLOW_REPOSITORY" ;;
            --verify)
                [[ "${3:-}" == "refs/remotes/origin/main^{commit}" ]] || exit 1
                printf '%s\\n' "$MAIN_TIP"
                ;;
            *) exit 1 ;;
        esac
        ;;
    cat-file)
        [[ "${2:-}" == "-e" ]] || exit 1
        requested="${3:0:40}"
        [[ "${3:-}" == "$requested^{commit}" ]] || exit 1
        case "$requested" in
            "$MAIN_1_SHA"|"$MAIN_2_SHA"|"$FORK_SHA") exit 0 ;;
            *) exit 1 ;;
        esac
        ;;
    merge-base)
        if [[ -n "$MERGE_BASE_EXIT" ]]; then
            exit "$MERGE_BASE_EXIT"
        fi
        if [[ "${3:-}" == "${4:-}" ]]; then
            exit 0
        fi
        if [[ "${3:-}" == "$MAIN_1_SHA" && "${4:-}" == "$MAIN_2_SHA" ]]; then
            exit 0
        fi
        exit 1
        ;;
    checkout)
        case "${3:-}" in
            "$MAIN_1_SHA"|"$MAIN_2_SHA"|"$FORK_SHA") exit 0 ;;
            *) exit 1 ;;
        esac
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
            "EXPECTED_DOCKER_TOKEN": "test-ghcr-token",
            "FAKE_CHMOD_EXIT": str(chmod_exit),
            "DEPLOY_ENV": "staging",
            "DEPLOY_REF": deploy_ref,
            "DEPLOY_SHA": deploy_sha,
            "MAIN_TIP": main_tip,
            "MAIN_1_SHA": MAIN_1_SHA,
            "MAIN_2_SHA": MAIN_2_SHA,
            "FORK_SHA": FORK_SHA,
            "MERGE_BASE_EXIT": "" if merge_base_exit is None else str(merge_base_exit),
            "SHALLOW_REPOSITORY": shallow_repository,
            "DIRTY_OUTPUT": dirty_output,
            "FETCH_EXIT": str(fetch_exit),
            "FETCH_CREATES_GRAFTS": "1" if fetch_creates_grafts else "0",
            "GRAFTS_PATH": str(grafts_path),
            "GIT_LOG": str(git_log),
            "GATE_LOG": str(gate_log),
            "IMAGE_REGISTRY": "ghcr.io/example/project",
            "IMAGE_TAG": image_tag or f"sha-{deploy_sha[:7]}",
            "VPS_APP_DIR": str(app_dir),
            "GHCR_USERNAME": "ghcr-user",
            "GHCR_TOKEN_B64": base64.b64encode(b"test-ghcr-token").decode("ascii"),
            "ghcr_token_b64": "must-not-remain-exported",
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
    return result, docker_log, gate_log, git_log, config_paths


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


def test_remote_deploy_preserves_credential_and_git_boundary_contracts():
    source = REMOTE_DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'GHCR_TOKEN_B64:?GHCR_TOKEN_B64 is required' in source
    assert 'ghcr_token_b64="$GHCR_TOKEN_B64"' in source
    assert 'unset GHCR_TOKEN_B64' in source
    assert 'export -n ghcr_token_b64' in source
    assert 'printf \'%s\' "$ghcr_token_b64" | base64 --decode | docker login ghcr.io' in source
    assert 'unset ghcr_token_b64' in source
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
    assert 'readonly DEPLOY_REF="refs/heads/main"' in source
    assert 'readonly DEPLOY_REMOTE_REF="refs/remotes/origin/main"' in source
    assert 'export GIT_NO_REPLACE_OBJECTS=1' in source
    assert 'git --no-replace-objects rev-parse --git-path info/grafts' in source
    assert '[[ -s "$grafts_path" ]]' in source
    assert 'git --no-replace-objects fetch --no-tags origin "$DEPLOY_REF:$DEPLOY_REMOTE_REF"' in source
    assert 'main_tip="$(git --no-replace-objects rev-parse --verify "$DEPLOY_REMOTE_REF^{commit}")"' in source
    assert 'git --no-replace-objects cat-file -e "$DEPLOY_SHA^{commit}"' in source
    assert 'git --no-replace-objects merge-base --is-ancestor "$DEPLOY_SHA" "$main_tip"' in source
    assert 'git --no-replace-objects checkout --detach "$DEPLOY_SHA"' in source
    assert "git rev-parse 'FETCH_HEAD^{commit}'" not in source
    assert "refs/tags/release-" not in source
    assert '[[ ! "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]]' in source
    assert '[[ ! "$IMAGE_TAG" =~ ^sha-[0-9a-f]{7}$ ]]' in source
    assert 'expected_image_tag="sha-${DEPLOY_SHA:0:7}"' in source
    assert '[[ "$IMAGE_TAG" != "$expected_image_tag" ]]' in source
    assert source.index('unset GHCR_TOKEN_B64') < source.index(
        'git --no-replace-objects status --porcelain'
    )
    assert source.index('git --no-replace-objects merge-base --is-ancestor') < source.index(
        'git --no-replace-objects checkout --detach'
    )
    assert source.index('git --no-replace-objects checkout --detach') < source.index(
        'docker login ghcr.io'
    )
    assert source.index('docker login ghcr.io') < source.index('run_gate "deploy')


@pytest.mark.parametrize(
    ("docker_exit", "chmod_exit", "expected_returncode"),
    ((0, 0, 0), (23, 0, 23), (0, 23, 23)),
)
def test_remote_deploy_cleans_docker_config_on_success_and_failures(
    tmp_path, docker_exit, chmod_exit, expected_returncode
):
    result, docker_log, gate_log, git_log, config_paths = _remote_deploy_harness(
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
        git_log_lines = git_log.read_text(encoding="utf-8").splitlines()
        assert git_log_lines[-1].endswith(f"checkout --detach {MAIN_2_SHA}")
        assert all(
            line.startswith("token=absent docker-auth=absent no-replace=1 | ")
            for line in git_log_lines
        )
    else:
        assert not docker_log.exists()
        assert not git_log.exists()

    if docker_exit == 0 and chmod_exit == 0:
        assert gate_log.read_text(encoding="utf-8").splitlines() == ["deploy", "smoke"]
    else:
        assert not gate_log.exists()


def test_remote_deploy_uses_canonical_main_ref_and_accepts_main_tip(tmp_path):
    result, docker_log, gate_log, git_log, config_paths = _remote_deploy_harness(
        tmp_path,
        deploy_ref="refs/tags/release-attacker-selected",
        deploy_sha=MAIN_2_SHA,
        main_tip=MAIN_2_SHA,
    )

    assert result.returncode == 0
    assert docker_log.exists()
    assert gate_log.read_text(encoding="utf-8").splitlines() == ["deploy", "smoke"]
    security_prefix = "token=absent docker-auth=absent no-replace=1 | "
    git_prefix = "--no-replace-objects "
    assert git_log.read_text(encoding="utf-8").splitlines() == [
        security_prefix + git_prefix + "status --porcelain --untracked-files=all",
        security_prefix + git_prefix + "rev-parse --git-path info/grafts",
        security_prefix + git_prefix + "rev-parse --is-shallow-repository",
        security_prefix
        + git_prefix
        + "fetch --no-tags origin refs/heads/main:refs/remotes/origin/main",
        security_prefix + git_prefix + "rev-parse --git-path info/grafts",
        security_prefix
        + git_prefix
        + "rev-parse --verify refs/remotes/origin/main^{commit}",
        security_prefix + git_prefix + f"cat-file -e {MAIN_2_SHA}^{{commit}}",
        security_prefix
        + git_prefix
        + f"merge-base --is-ancestor {MAIN_2_SHA} {MAIN_2_SHA}",
        security_prefix + git_prefix + f"checkout --detach {MAIN_2_SHA}",
    ]
    assert all(not Path(path).exists() for path in config_paths)


def test_remote_deploy_accepts_an_old_main_ancestor_for_rollback(tmp_path):
    result, docker_log, gate_log, git_log, config_paths = _remote_deploy_harness(
        tmp_path,
        deploy_sha=MAIN_1_SHA,
        main_tip=MAIN_2_SHA,
    )

    assert result.returncode == 0
    assert docker_log.exists()
    assert gate_log.read_text(encoding="utf-8").splitlines() == ["deploy", "smoke"]
    git_commands = git_log.read_text(encoding="utf-8").splitlines()
    assert any(
        command.endswith(f"merge-base --is-ancestor {MAIN_1_SHA} {MAIN_2_SHA}")
        for command in git_commands
    )
    assert any(command.endswith(f"checkout --detach {MAIN_1_SHA}") for command in git_commands)
    assert all(not Path(path).exists() for path in config_paths)


@pytest.mark.parametrize(
    ("options", "message"),
    (
        ({"dirty_output": " M infra/scripts/deploy.sh\\n"}, "worktree is dirty"),
        ({"shallow_repository": "true"}, "shallow VPS repository"),
        ({"deploy_sha": MISSING_SHA}, "commit object is missing"),
        ({"deploy_sha": FORK_SHA}, "not an ancestor"),
        (
            {"deploy_sha": FORK_SHA, "merge_base_exit": 128},
            "unable to verify DEPLOY_SHA ancestry",
        ),
        ({"fetch_exit": 23}, ""),
        (
            {"grafts_content": f"{MAIN_2_SHA} {FORK_SHA}\\n"},
            "legacy Git grafts are not allowed",
        ),
        (
            {"fetch_creates_grafts": True},
            "legacy Git grafts are not allowed",
        ),
    ),
)
def test_remote_deploy_rejects_untrusted_git_states_before_login_or_deploy(
    tmp_path, options, message
):
    result, docker_log, gate_log, git_log, config_paths = _remote_deploy_harness(
        tmp_path,
        main_tip=MAIN_2_SHA,
        **options,
    )

    assert result.returncode != 0
    if message:
        assert message in result.stdout
    assert not docker_log.exists()
    assert not gate_log.exists()
    assert "checkout --detach" not in git_log.read_text(encoding="utf-8")
    assert all(not Path(path).exists() for path in config_paths)


def test_git_replace_and_legacy_grafts_can_rewrite_ancestry_without_remote_gates(
    tmp_path,
):
    repository = tmp_path / "git-history"
    repository.mkdir()

    def git(*args: str, env: dict[str, str] | None = None, check: bool = True):
        return subprocess.run(
            ["git", *args],
            cwd=repository,
            env=env,
            text=True,
            capture_output=True,
            check=check,
        )

    git("init", "-q", ".")
    git("config", "user.name", "CI contract test")
    git("config", "user.email", "ci-contract@example.invalid")
    history_file = repository / "history.txt"
    history_file.write_text("main-1\n", encoding="utf-8")
    git("add", "history.txt")
    git("commit", "-q", "-m", "main 1")
    git("branch", "-M", "main")
    main_1 = git("rev-parse", "HEAD").stdout.strip()

    history_file.write_text("main-2\n", encoding="utf-8")
    git("commit", "-q", "-am", "main 2")
    main_2 = git("rev-parse", "HEAD").stdout.strip()

    git("checkout", "-q", "--orphan", "fork")
    git("rm", "-q", "-rf", ".")
    history_file.write_text("fork\n", encoding="utf-8")
    git("add", "history.txt")
    git("commit", "-q", "-m", "fork")
    fork = git("rev-parse", "HEAD").stdout.strip()

    assert git("merge-base", "--is-ancestor", main_1, main_2, check=False).returncode == 0
    assert git("merge-base", "--is-ancestor", fork, main_2, check=False).returncode == 1

    git("replace", "--graft", main_2, fork)
    assert git("merge-base", "--is-ancestor", fork, main_2, check=False).returncode == 0
    no_replace_env = os.environ.copy()
    no_replace_env["GIT_NO_REPLACE_OBJECTS"] = "1"
    assert (
        git(
            "merge-base",
            "--is-ancestor",
            fork,
            main_2,
            env=no_replace_env,
            check=False,
        ).returncode
        == 1
    )
    git("replace", "-d", main_2)

    grafts_path = Path(git("rev-parse", "--git-path", "info/grafts").stdout.strip())
    if not grafts_path.is_absolute():
        grafts_path = repository / grafts_path
    grafts_path.parent.mkdir(parents=True, exist_ok=True)
    grafts_path.write_text(f"{main_2} {fork}\n", encoding="utf-8")
    assert git("merge-base", "--is-ancestor", fork, main_2, check=False).returncode == 0
    assert (
        git(
            "merge-base",
            "--is-ancestor",
            fork,
            main_2,
            env=no_replace_env,
            check=False,
        ).returncode
        == 0
    )


@pytest.mark.parametrize(
    "image_tag",
    ("latest", "prod-current", "sha-bbbbbbb", "main-aaaaaaa"),
)
def test_remote_deploy_rejects_mutable_or_mismatched_image_tags_before_git_or_login(
    tmp_path, image_tag
):
    result, docker_log, gate_log, git_log, config_paths = _remote_deploy_harness(
        tmp_path,
        deploy_sha="a" * 40,
        image_tag=image_tag,
    )

    assert result.returncode != 0
    assert "IMAGE_TAG" in result.stdout
    assert not docker_log.exists()
    assert not gate_log.exists()
    assert not git_log.exists()
    assert all(not Path(path).exists() for path in config_paths)


@pytest.mark.parametrize("deploy_sha", ("a" * 39, "A" * 40, "g" * 40))
def test_remote_deploy_rejects_invalid_deploy_sha_before_git_or_login(tmp_path, deploy_sha):
    result, docker_log, gate_log, git_log, config_paths = _remote_deploy_harness(
        tmp_path,
        deploy_sha=deploy_sha,
        image_tag="sha-aaaaaaa",
    )

    assert result.returncode != 0
    assert "40-character lowercase commit SHA" in result.stdout
    assert not docker_log.exists()
    assert not gate_log.exists()
    assert not git_log.exists()
    assert all(not Path(path).exists() for path in config_paths)


def test_deploy_validation_requires_known_hosts_secret():
    source = VALIDATE_DEPLOY_ENV_SCRIPT.read_text(encoding="utf-8")

    assert '"VPS_KNOWN_HOSTS:VPS_KNOWN_HOSTS"' in source


VALIDATE_TRUSTED_REQUEST_SCRIPT = (
    REPOSITORY_ROOT / ".github/scripts/validate-trusted-deploy-request.py"
)
_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "validate_trusted_deploy_request", VALIDATE_TRUSTED_REQUEST_SCRIPT
)
if _VALIDATOR_SPEC is None or _VALIDATOR_SPEC.loader is None:
    raise RuntimeError("unable to load trusted request validator")
trusted_request_validator = importlib.util.module_from_spec(_VALIDATOR_SPEC)
_VALIDATOR_SPEC.loader.exec_module(trusted_request_validator)


def _valid_trusted_request(
    *, request_type: str = "deploy", environment: str | None = None
) -> dict[str, str]:
    deploy_sha = "a" * 40
    return {
        "schema_version": "trusted-deploy-request/v1",
        "request_type": request_type,
        "environment": environment or ("staging" if request_type == "deploy" else "prod"),
        "image_tag": "sha-aaaaaaa",
        "deploy_sha": deploy_sha,
    }


def _trusted_request_zip(
    request: dict[str, str],
    *,
    member_name: str = "trusted-deploy-request.json",
    extra_member: bool = False,
    symlink: bool = False,
    oversized: bool = False,
    corrupt_crc: bool = False,
    encrypted: bool = False,
    dos_directory: bool = False,
    extra_entries: int = 0,
    central_extra_bytes: int = 0,
    central_file_size: int | None = None,
    central_compress_size: int | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
    corrupt_deflate: bool = False,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(member_name)
        info.compress_type = compression
        if symlink:
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
        if dos_directory:
            info.external_attr |= 0x10
        if central_extra_bytes:
            info.extra = b"x" * central_extra_bytes
        payload = (
            b"x" * (64 * 1024 + 1)
            if oversized
            else json.dumps(request).encode("utf-8")
        )
        archive.writestr(info, payload)
        if extra_member:
            archive.writestr("extra.txt", b"ignored")
        for index in range(extra_entries):
            extra_info = zipfile.ZipInfo(f"extra-{index}.txt")
            extra_info.compress_type = zipfile.ZIP_DEFLATED
            if central_extra_bytes:
                extra_info.extra = b"x" * central_extra_bytes
            archive.writestr(extra_info, b"ignored")

    archive_bytes = bytearray(output.getvalue())
    central_directory = archive_bytes.index(bytes.fromhex("504b0102"))
    local_header = archive_bytes.index(bytes.fromhex("504b0304"))
    if corrupt_deflate:
        filename_size, extra_size = struct.unpack_from("<HH", archive_bytes, local_header + 26)
        data_offset = local_header + 30 + filename_size + extra_size
        archive_bytes[data_offset] ^= 0xFF
    if corrupt_crc:
        archive_bytes[central_directory + 16] ^= 0x01
    if central_file_size is not None:
        struct.pack_into("<L", archive_bytes, central_directory + 24, central_file_size)
    if central_compress_size is not None:
        struct.pack_into("<L", archive_bytes, central_directory + 20, central_compress_size)
    if encrypted:
        struct.pack_into("<H", archive_bytes, central_directory + 8, 0x1)
        struct.pack_into("<H", archive_bytes, local_header + 6, 0x1)
    return bytes(archive_bytes)


def test_trusted_request_validator_accepts_deploy_and_rollback_and_normalizes_output(
    tmp_path, capsys
):
    for request_type, filename in (
        ("deploy", "trusted-deploy-request.json"),
        ("rollback", "trusted-rollback-request.json"),
    ):
        request = _valid_trusted_request(request_type=request_type, environment="staging")
        json_path = tmp_path / filename
        json_path.write_text(json.dumps(dict(reversed(list(request.items())))), encoding="utf-8")

        assert trusted_request_validator.validate_request_file(json_path) == request
        assert trusted_request_validator.main([str(json_path)]) == 0
        assert capsys.readouterr().out == (
            json.dumps(request, ensure_ascii=True, separators=(",", ":")) + "\n"
        )

        zip_path = tmp_path / f"{request_type}.zip"
        zip_path.write_bytes(_trusted_request_zip(request, member_name=filename))
        assert trusted_request_validator.validate_request_zip(zip_path) == request
        assert trusted_request_validator.main(["--artifact-zip", str(zip_path)]) == 0
        assert capsys.readouterr().out == (
            json.dumps(request, ensure_ascii=True, separators=(",", ":")) + "\n"
        )


@pytest.mark.parametrize(
    ("label", "payload", "message"),
    (
        (
            "extra-key",
            {**_valid_trusted_request(), "unexpected": "value"},
            "request JSON keys do not match the trusted request schema",
        ),
        (
            "wrong-type",
            {**_valid_trusted_request(), "image_tag": 123},
            "request fields must be non-empty strings",
        ),
        (
            "unsupported-schema",
            {**_valid_trusted_request(), "schema_version": "trusted-deploy-request/v2"},
            "unsupported trusted request schema",
        ),
        (
            "invalid-request-type",
            {**_valid_trusted_request(), "request_type": "promote"},
            "request_type must be deploy or rollback",
        ),
        (
            "invalid-environment",
            {**_valid_trusted_request(), "environment": "qa"},
            "environment must be staging or prod",
        ),
        (
            "bad-sha",
            {**_valid_trusted_request(), "deploy_sha": "A" * 40},
            "deploy_sha must be a 40-character lowercase hexadecimal SHA",
        ),
        (
            "bad-tag",
            {**_valid_trusted_request(), "image_tag": "sha-zzzzzzz"},
            "image_tag must use the sha-<7 lowercase hexadecimal> format",
        ),
        (
            "mismatch",
            {**_valid_trusted_request(), "deploy_sha": "b" * 40},
            "image_tag must match the deploy_sha prefix",
        ),
        (
            "control-character",
            {**_valid_trusted_request(), "schema_version": "trusted-deploy-request/v1\n"},
            "request fields must not contain control characters",
        ),
        (
            "empty-value",
            {**_valid_trusted_request(), "environment": ""},
            "request fields must be non-empty strings",
        ),
    ),
)
def test_trusted_request_validator_rejects_invalid_json_contract(
    label, payload, message
):
    del label
    with pytest.raises(trusted_request_validator.RequestValidationError, match=message):
        trusted_request_validator.validate_request_bytes(json.dumps(payload).encode("utf-8"))


@pytest.mark.parametrize(
    ("label", "payload", "message"),
    (
        (
            "duplicate-key",
            b'{"schema_version":"trusted-deploy-request/v1","schema_version":"trusted-deploy-request/v1"}',
            "request JSON contains duplicate keys",
        ),
        (
            "nonstandard-number",
            b'{"schema_version":"trusted-deploy-request/v1","request_type":"deploy","environment":"staging","image_tag":NaN,"deploy_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
            "request JSON contains a non-standard number",
        ),
        ("invalid-utf8", b"\xff", "request JSON must be UTF-8"),
        ("non-object", b"[]", "request JSON must be an object"),
    ),
)
def test_trusted_request_validator_rejects_invalid_json_encoding(
    label, payload, message
):
    del label
    with pytest.raises(trusted_request_validator.RequestValidationError, match=message):
        trusted_request_validator.validate_request_bytes(payload)


@pytest.mark.parametrize(
    ("label", "member_name", "extra_member", "symlink", "oversized", "corrupt_crc", "message"),
    (
        (
            "extra",
            "trusted-deploy-request.json",
            True,
            False,
            False,
            False,
            "request artifact must contain exactly one file",
        ),
        (
            "traversal",
            "../trusted-deploy-request.json",
            False,
            False,
            False,
            False,
            "archive member path must not contain parent traversal",
        ),
        (
            "absolute",
            "/trusted-deploy-request.json",
            False,
            False,
            False,
            False,
            "archive member path must not be absolute",
        ),
        (
            "backslash",
            "trusted-deploy-request.json\\nested",
            False,
            False,
            False,
            False,
            "archive member path must not contain backslashes",
        ),
        (
            "directory",
            "trusted-deploy-request.json/",
            False,
            False,
            False,
            False,
            "request artifact must not contain a directory",
        ),
        (
            "symlink",
            "trusted-deploy-request.json",
            False,
            True,
            False,
            False,
            "request artifact must contain a regular file",
        ),
        (
            "size",
            "trusted-deploy-request.json",
            False,
            False,
            True,
            False,
            "archive member has an invalid uncompressed size",
        ),
        (
            "crc",
            "trusted-deploy-request.json",
            False,
            False,
            False,
            True,
            "archive member failed integrity checks",
        ),
    ),
)
def test_trusted_request_validator_rejects_unsafe_zip_artifacts(
    tmp_path,
    label,
    member_name,
    extra_member,
    symlink,
    oversized,
    corrupt_crc,
    message,
):
    zip_path = tmp_path / f"{label}.zip"
    zip_path.write_bytes(
        _trusted_request_zip(
            _valid_trusted_request(),
            member_name=member_name,
            extra_member=extra_member,
            symlink=symlink,
            oversized=oversized,
            corrupt_crc=corrupt_crc,
        )
    )

    with pytest.raises(trusted_request_validator.RequestValidationError, match=message):
        trusted_request_validator.validate_request_zip(zip_path)


# zipfile enforces ZipInfo.file_size while reading; oversized declarations fail before
# the defensive post-read expansion check, so this suite does not claim that branch.
@pytest.mark.parametrize(
    ("label", "options", "message"),
    (
        (
            "dos-directory",
            {"dos_directory": True},
            "request artifact must not contain a directory",
        ),
        (
            "encrypted",
            {"encrypted": True},
            "request artifact must not contain an encrypted file",
        ),
        (
            "corrupt-deflate",
            {"corrupt_deflate": True},
            "archive member failed integrity checks",
        ),
        (
            "unsupported-lzma",
            {"compression": zipfile.ZIP_LZMA},
            "archive member uses an unsupported compression method",
        ),
        (
            "compressed-size-mismatch",
            {"central_compress_size": 0},
            "archive member failed integrity checks",
        ),
        (
            "uncompressed-size-mismatch",
            {"central_file_size": 1},
            "archive member failed integrity checks",
        ),
        (
            "filename-type-mismatch",
            {"member_name": "trusted-rollback-request.json"},
            "request filename does not match request_type",
        ),
    ),
)
def test_trusted_request_validator_rejects_zip_metadata_and_type_mismatches(
    tmp_path, label, options, message
):
    zip_path = tmp_path / f"{label}.zip"
    zip_path.write_bytes(_trusted_request_zip(_valid_trusted_request(), **options))

    with pytest.raises(trusted_request_validator.RequestValidationError, match=message):
        trusted_request_validator.validate_request_zip(zip_path)


def test_trusted_request_validator_rejects_archive_resource_limits():
    with pytest.raises(
        trusted_request_validator.RequestValidationError,
        match="request artifact exceeds the archive size limit",
    ):
        trusted_request_validator.validate_request_zip_bytes(b"x" * (1024 * 1024 + 1))

    too_many_entries = _trusted_request_zip(_valid_trusted_request(), extra_entries=17)
    with pytest.raises(
        trusted_request_validator.RequestValidationError,
        match="request artifact has too many entries",
    ):
        trusted_request_validator.validate_request_zip_bytes(too_many_entries)

    oversized_central_directory = _trusted_request_zip(
        _valid_trusted_request(), extra_entries=15, central_extra_bytes=5000
    )
    with pytest.raises(
        trusted_request_validator.RequestValidationError,
        match="central directory exceeds the size limit",
    ):
        trusted_request_validator.validate_request_zip_bytes(oversized_central_directory)


def test_trusted_request_validator_rejects_invalid_zip_bytes_and_supports_stdin(
    monkeypatch, capsys
):
    with pytest.raises(
        trusted_request_validator.RequestValidationError,
        match="request artifact is not a valid ZIP archive",
    ):
        trusted_request_validator.validate_request_zip_bytes(b"not a ZIP")

    request = _valid_trusted_request()
    stdin = type("BinaryStdin", (), {"buffer": io.BytesIO(json.dumps(request).encode())})()
    monkeypatch.setattr(trusted_request_validator.sys, "stdin", stdin)
    assert trusted_request_validator.main([]) == 0
    assert json.loads(capsys.readouterr().out) == request


def test_trusted_request_validator_bounds_plain_json_file_reads(tmp_path):
    request_path = tmp_path / "oversized.json"
    request_path.write_bytes(b"x" * (64 * 1024 + 1))

    with pytest.raises(
        trusted_request_validator.RequestValidationError,
        match="request JSON exceeds the size limit or cannot be read",
    ):
        trusted_request_validator.validate_request_file(request_path)


def test_trusted_request_validator_rejects_unsafe_path_inputs_without_blocking(
    tmp_path,
):
    if not all(hasattr(os, attribute) for attribute in ("O_NOFOLLOW", "mkfifo", "symlink")):
        pytest.skip("safe path primitives are unavailable on this platform")

    request = _valid_trusted_request()
    json_target = tmp_path / "request.json"
    json_target.write_text(json.dumps(request), encoding="utf-8")
    zip_target = tmp_path / "request.zip"
    zip_target.write_bytes(_trusted_request_zip(request))

    symlink_json = tmp_path / "request-link.json"
    symlink_json.symlink_to(json_target)
    symlink_zip = tmp_path / "request-link.zip"
    symlink_zip.symlink_to(zip_target)
    fifo_json = tmp_path / "request.pipe"
    os.mkfifo(fifo_json)
    directory = tmp_path / "request-directory"
    directory.mkdir()

    def assert_rejected_without_traceback(args: list[str], path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_TRUSTED_REQUEST_SCRIPT),
                *args,
                str(path),
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        assert result.returncode != 0
        assert result.stdout == ""
        assert result.stderr.startswith("error:")
        assert "Traceback" not in result.stderr

    try:
        for args, path in (
            ([], symlink_json),
            (["--artifact-zip"], symlink_zip),
            ([], fifo_json),
            (["--artifact-zip"], fifo_json),
            ([], directory),
            (["--artifact-zip"], directory),
        ):
            assert_rejected_without_traceback(args, path)
    finally:
        fifo_json.unlink()


TRUSTED_IMAGE_PUBLICATION_SCRIPT = (
    REPOSITORY_ROOT / ".github/scripts/validate-trusted-image-publication.py"
)
_TRUSTED_IMAGE_PUBLICATION_SPEC = importlib.util.spec_from_file_location(
    "validate_trusted_image_publication", TRUSTED_IMAGE_PUBLICATION_SCRIPT
)
if (
    _TRUSTED_IMAGE_PUBLICATION_SPEC is None
    or _TRUSTED_IMAGE_PUBLICATION_SPEC.loader is None
):
    raise RuntimeError("unable to load trusted image publication validator")
trusted_image_publication_validator = importlib.util.module_from_spec(
    _TRUSTED_IMAGE_PUBLICATION_SPEC
)
_TRUSTED_IMAGE_PUBLICATION_SPEC.loader.exec_module(trusted_image_publication_validator)

PUBLICATION_REPOSITORY = "Example/Project"
PUBLICATION_SHA = "c" * 40
PUBLICATION_DIGESTS = {
    "web": f"sha256:{'1' * 64}",
    "api": f"sha256:{'2' * 64}",
    "worker": f"sha256:{'3' * 64}",
}


def _valid_image_publication(*, run_attempt: str = "1") -> dict[str, Any]:
    registry = "ghcr.io/example/project"
    return {
        "schema_version": "trusted-image-publication/v1",
        "repository": PUBLICATION_REPOSITORY,
        "workflow_id": "7001",
        "run_id": "8001",
        "run_attempt": run_attempt,
        "deploy_sha": PUBLICATION_SHA,
        "image_tag": f"sha-{PUBLICATION_SHA}",
        "images": {
            "web": {
                "repository": f"{registry}/ai-reader-web",
                "digest": PUBLICATION_DIGESTS["web"],
            },
            "api": {
                "repository": f"{registry}/ai-reader-api",
                "digest": PUBLICATION_DIGESTS["api"],
            },
            "worker": {
                "repository": f"{registry}/ai-reader-worker",
                "digest": PUBLICATION_DIGESTS["worker"],
            },
        },
    }


def test_ci_publishes_full_sha_and_legacy_alias_without_switching_staging():
    workflow = _load_workflow(CI_WORKFLOW)
    images = workflow["jobs"]["images"]
    meta = next(step for step in images["steps"] if step.get("id") == "meta")
    meta_script = meta["run"]

    assert '[[ "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]]' in meta_script
    assert 'canonical_image_tag="sha-${DEPLOY_SHA}"' in meta_script
    assert 'legacy_image_tag="sha-${short_sha}"' in meta_script
    assert 'echo "image_tag=${legacy_image_tag}"' in meta_script
    assert 'echo "canonical_image_tag=${canonical_image_tag}"' in meta_script
    for image_name in ("web", "api", "worker"):
        assert f'echo "${{image_registry}}/ai-reader-{image_name}:${{canonical_image_tag}}"' in meta_script
        assert f'echo "${{image_registry}}/ai-reader-{image_name}:${{legacy_image_tag}}"' in meta_script

    assert images["outputs"]["image_tag"] == "${{ steps.meta.outputs.image_tag }}"
    assert images["outputs"]["canonical_image_tag"] == (
        "${{ steps.meta.outputs.canonical_image_tag }}"
    )
    deploy = workflow["jobs"]["deploy-staging"]
    deploy_step = next(step for step in deploy["steps"] if step.get("name") == "Deploy staging on VPS")
    assert deploy_step["env"]["IMAGE_TAG"] == "${{ needs.images.outputs.image_tag }}"
    assert "canonical_image_tag" not in deploy_step["env"]
    assert not any(key.endswith("DIGEST") for key in deploy_step["env"])


def test_ci_publication_uses_push_digests_and_checks_oci_revision_before_upload():
    workflow = _load_workflow(CI_WORKFLOW)
    images = workflow["jobs"]["images"]
    steps = images["steps"]
    build_ids = {
        step["name"]: step.get("id")
        for step in steps
        if step.get("uses") == "docker/build-push-action@v6"
    }
    assert build_ids == {
        "Build and push ai-reader-web": "web_build",
        "Build and push ai-reader-api": "api_build",
        "Build and push ai-reader-worker": "worker_build",
    }
    for step in steps:
        if step.get("uses") == "docker/build-push-action@v6":
            assert "org.opencontainers.image.revision=${{ steps.meta.outputs.deploy_sha }}" in step[
                "with"
            ]["labels"]

    publication = next(
        step for step in steps if step.get("name") == "Validate and write image publication evidence"
    )
    assert publication["env"] == {
        "DEPLOY_SHA": "${{ steps.meta.outputs.deploy_sha }}",
        "IMAGE_REGISTRY": "${{ steps.meta.outputs.image_registry }}",
        "CANONICAL_IMAGE_TAG": "${{ steps.meta.outputs.canonical_image_tag }}",
        "WEB_DIGEST": "${{ steps.web_build.outputs.digest }}",
        "API_DIGEST": "${{ steps.api_build.outputs.digest }}",
        "WORKER_DIGEST": "${{ steps.worker_build.outputs.digest }}",
        "WORKFLOW_ID": "${{ steps.run_identity.outputs.workflow_id }}",
        "RUN_ID": "${{ github.run_id }}",
        "RUN_ATTEMPT": "${{ github.run_attempt }}",
    }
    script = publication["run"]
    assert "set -euo pipefail" in script
    assert "^sha256:[0-9a-f]{64}$" in script
    assert '[[ "$pushed_digest" =~ $digest_pattern ]]' in script
    assert "docker buildx imagetools inspect" in script
    assert '--raw > "$raw_manifest"' in script
    assert 'inspected_digest="sha256:$(sha256sum' in script
    assert "expected exactly one runnable Linux image manifest" in script
    assert '.["org.opencontainers.image.revision"]' in script
    assert '[[ "$inspected_digest" == "$pushed_digest" ]]' in script
    assert '[[ "$inspected_revision" == "$DEPLOY_SHA" ]]' in script
    for digest in ("WEB_DIGEST", "API_DIGEST", "WORKER_DIGEST"):
        assert f'"${digest}"' in script
    assert "trusted-image-publication/v1" in script
    assert "validate-trusted-image-publication.py" in script


def test_ci_publication_artifact_is_exact_attempt_scoped_and_non_overwriting():
    workflow = _load_workflow(CI_WORKFLOW)
    steps = workflow["jobs"]["images"]["steps"]
    identity = next(step for step in steps if step.get("id") == "run_identity")
    assert identity["uses"] == "actions/github-script@v7"
    assert identity["env"]["EXPECTED_RUN_ID"] == "${{ github.run_id }}"
    assert identity["env"]["EXPECTED_RUN_ATTEMPT"] == "${{ github.run_attempt }}"
    assert identity["env"]["EXPECTED_HEAD_SHA"] == "${{ steps.meta.outputs.deploy_sha }}"
    assert "getWorkflowRun" in identity["with"]["script"]
    assert "run.run_attempt !== expectedAttempt" in identity["with"]["script"]
    assert "run.head_sha !== process.env.EXPECTED_HEAD_SHA" in identity["with"]["script"]

    upload = next(
        step
        for step in steps
        if step.get("name") == "Upload trusted image publication evidence"
    )
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["with"] == {
        "name": "trusted-image-publication-${{ github.run_id }}-attempt-${{ github.run_attempt }}",
        "path": "output/evidence/trusted-image-publication/trusted-image-publication.json",
        "if-no-files-found": "error",
        "retention-days": 90,
        "overwrite": False,
    }


def test_trusted_image_publication_validator_accepts_initial_and_rerun_attempts(
    tmp_path, capsys
):
    for attempt in ("1", "2", "19"):
        publication = _valid_image_publication(run_attempt=attempt)
        json_path = tmp_path / f"publication-{attempt}.json"
        json_path.write_text(json.dumps(publication), encoding="utf-8")
        assert trusted_image_publication_validator.validate_publication_file(
            json_path, expected_repository=PUBLICATION_REPOSITORY
        ) == publication

        zip_path = tmp_path / f"publication-{attempt}.zip"
        zip_path.write_bytes(
            _trusted_request_zip(
                publication, member_name="trusted-image-publication.json"
            )
        )
        assert trusted_image_publication_validator.validate_publication_zip(
            zip_path, expected_repository=PUBLICATION_REPOSITORY
        ) == publication
        assert (
            trusted_image_publication_validator.main(
                [
                    "--expected-repository",
                    PUBLICATION_REPOSITORY,
                    "--artifact-zip",
                    str(zip_path),
                ]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out) == publication


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("extra-field", "publication JSON keys do not match"),
        ("missing-digest", "images.web keys do not match"),
        ("wrong-repository", "images.api.repository mismatch"),
        ("short-digest", "images.worker.digest must be a lowercase sha256 digest"),
        ("uppercase-digest", "images.web.digest must be a lowercase sha256 digest"),
        ("bad-tag", "image_tag must equal"),
        ("bad-attempt", "run_attempt must be a canonical positive integer string"),
    ),
)
def test_trusted_image_publication_validator_rejects_schema_mismatches(mutation, message):
    publication = _valid_image_publication()
    if mutation == "extra-field":
        publication["unexpected"] = "value"
    elif mutation == "missing-digest":
        del publication["images"]["web"]["digest"]
    elif mutation == "wrong-repository":
        publication["images"]["api"]["repository"] = (
            "ghcr.io/example/project/ai-reader-worker"
        )
    elif mutation == "short-digest":
        publication["images"]["worker"]["digest"] = "sha256:1234"
    elif mutation == "uppercase-digest":
        publication["images"]["web"]["digest"] = f"sha256:{'A' * 64}"
    elif mutation == "bad-tag":
        publication["image_tag"] = f"sha-{PUBLICATION_SHA[:7]}"
    elif mutation == "bad-attempt":
        publication["run_attempt"] = "02"
    with pytest.raises(
        trusted_image_publication_validator.PublicationValidationError, match=message
    ):
        trusted_image_publication_validator.validate_publication(
            publication, expected_repository=PUBLICATION_REPOSITORY
        )


def test_trusted_image_publication_validator_rejects_duplicate_keys():
    payload = json.dumps(_valid_image_publication(), separators=(",", ":"))
    payload = payload.replace(
        '"workflow_id":"7001"', '"workflow_id":"7001","workflow_id":"7002"'
    )
    with pytest.raises(
        trusted_image_publication_validator.PublicationValidationError,
        match="publication JSON contains duplicate keys",
    ):
        trusted_image_publication_validator.validate_publication_bytes(
            payload.encode("utf-8"), expected_repository=PUBLICATION_REPOSITORY
        )


@pytest.mark.parametrize(
    ("label", "options", "message"),
    (
        (
            "extra-member",
            {"extra_member": True},
            "publication artifact must contain exactly one file",
        ),
        (
            "traversal",
            {"member_name": "../trusted-image-publication.json"},
            "archive member path must not contain parent traversal",
        ),
        (
            "symlink",
            {"symlink": True},
            "publication artifact must contain a regular file",
        ),
        (
            "oversized",
            {"oversized": True},
            "archive member has an invalid uncompressed size",
        ),
        (
            "encrypted",
            {"encrypted": True},
            "publication artifact must not contain an encrypted file",
        ),
        (
            "compression",
            {"compression": zipfile.ZIP_LZMA},
            "archive member uses an unsupported compression method",
        ),
    ),
)
def test_trusted_image_publication_validator_rejects_unsafe_zip(
    tmp_path, label, options, message
):
    options = {"member_name": "trusted-image-publication.json", **options}
    zip_path = tmp_path / f"{label}.zip"
    zip_path.write_bytes(_trusted_request_zip(_valid_image_publication(), **options))
    with pytest.raises(
        trusted_image_publication_validator.PublicationValidationError, match=message
    ):
        trusted_image_publication_validator.validate_publication_zip(
            zip_path, expected_repository=PUBLICATION_REPOSITORY
        )


def test_trusted_image_publication_validator_rejects_archive_resource_limits():
    with pytest.raises(
        trusted_image_publication_validator.PublicationValidationError,
        match="publication artifact exceeds the archive size limit",
    ):
        trusted_image_publication_validator.validate_publication_zip_bytes(
            b"x" * (1024 * 1024 + 1), expected_repository=PUBLICATION_REPOSITORY
        )

    archive = _trusted_request_zip(
        _valid_image_publication(),
        member_name="trusted-image-publication.json",
        extra_entries=17,
    )
    with pytest.raises(
        trusted_image_publication_validator.PublicationValidationError,
        match="publication artifact has too many entries",
    ):
        trusted_image_publication_validator.validate_publication_zip_bytes(
            archive, expected_repository=PUBLICATION_REPOSITORY
        )


TRUSTED_WORKFLOW_RUN_SCRIPT = (
    REPOSITORY_ROOT / ".github/scripts/validate-trusted-workflow-run.py"
)
_TRUSTED_WORKFLOW_RUN_SPEC = importlib.util.spec_from_file_location(
    "validate_trusted_workflow_run", TRUSTED_WORKFLOW_RUN_SCRIPT
)
if _TRUSTED_WORKFLOW_RUN_SPEC is None or _TRUSTED_WORKFLOW_RUN_SPEC.loader is None:
    raise RuntimeError("unable to load trusted workflow-run validator")
trusted_workflow_run_validator = importlib.util.module_from_spec(_TRUSTED_WORKFLOW_RUN_SPEC)
_TRUSTED_WORKFLOW_RUN_SPEC.loader.exec_module(trusted_workflow_run_validator)

TRUSTED_REPOSITORY = "example/project"
TRUSTED_REPOSITORY_ID = 7001
TRUSTED_REQUEST_RUN_ID = 8001
TRUSTED_REQUEST_WORKFLOW_ID = 8101
TRUSTED_CI_WORKFLOW_ID = 8199
TRUSTED_CI_RUN_ID = 8201
TRUSTED_CI_RUN_ATTEMPT = 2
TRUSTED_TARGET_SHA = "a" * 40
TRUSTED_REQUEST_HEAD_SHA = "b" * 40


def _trusted_image_publication() -> dict[str, Any]:
    publication = _valid_image_publication(run_attempt=str(TRUSTED_CI_RUN_ATTEMPT))
    publication.update(
        {
            "repository": TRUSTED_REPOSITORY,
            "workflow_id": str(TRUSTED_CI_WORKFLOW_ID),
            "run_id": str(TRUSTED_CI_RUN_ID),
            "deploy_sha": TRUSTED_TARGET_SHA,
            "image_tag": f"sha-{TRUSTED_TARGET_SHA}",
        }
    )
    return publication


def _trusted_workflow_allowlist(
    *,
    request_workflow_id: int | None = TRUSTED_REQUEST_WORKFLOW_ID,
    ci_workflow_id: int | None = TRUSTED_CI_WORKFLOW_ID,
) -> dict[str, Any]:
    return {
        "schema_version": "trusted-workflow-ids/v1",
        "default_branch": "main",
        "request_workflows": {
            "deploy-staging": {
                "path": ".github/workflows/deploy-staging.yml",
                "name": "deploy-staging",
                "id": request_workflow_id,
                "artifact": "trusted-staging-deploy-request",
                "request_type": "deploy",
                "environment": "staging",
            },
            "deploy-prod": {
                "path": ".github/workflows/deploy-prod.yml",
                "name": "deploy-prod",
                "id": request_workflow_id,
                "artifact": "trusted-production-deploy-request",
                "request_type": "deploy",
                "environment": "prod",
            },
            "rollback": {
                "path": ".github/workflows/rollback.yml",
                "name": "rollback",
                "id": request_workflow_id,
                "artifact": "trusted-rollback-request",
                "request_type": "rollback",
                "environment": "from-request-after-validation",
            },
        },
        "ci_workflow": {
            "path": ".github/workflows/ci.yml",
            "name": "ci",
            "id": ci_workflow_id,
        },
    }


def _trusted_repository_identity() -> dict[str, Any]:
    return {"id": TRUSTED_REPOSITORY_ID, "full_name": TRUSTED_REPOSITORY}


def _trusted_workflow_run_fixture() -> tuple[dict[str, Any], dict[str, Any], Any]:
    repository = _trusted_repository_identity()
    head_repository = copy.deepcopy(repository)
    request_run = {
        "id": TRUSTED_REQUEST_RUN_ID,
        "workflow_id": TRUSTED_REQUEST_WORKFLOW_ID,
        "path": ".github/workflows/deploy-staging.yml",
        "name": "deploy-staging",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": TRUSTED_REQUEST_HEAD_SHA,
        "ref": "refs/heads/main",
        "repository": copy.deepcopy(repository),
        "head_repository": head_repository,
    }
    event = {"workflow_run": copy.deepcopy(request_run)}
    request = _valid_trusted_request(environment="staging")
    artifact = {
        "id": 8301,
        "name": "trusted-staging-deploy-request",
        "expired": False,
        "workflow_run": {
            "id": TRUSTED_REQUEST_RUN_ID,
            "repository_id": TRUSTED_REPOSITORY_ID,
            "head_repository_id": TRUSTED_REPOSITORY_ID,
            "head_branch": "main",
            "head_sha": TRUSTED_REQUEST_HEAD_SHA,
        },
    }
    ci_run = {
        "id": TRUSTED_CI_RUN_ID,
        "run_attempt": TRUSTED_CI_RUN_ATTEMPT,
        "workflow_id": TRUSTED_CI_WORKFLOW_ID,
        "path": ".github/workflows/ci.yml",
        "name": "ci",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": TRUSTED_TARGET_SHA,
        "ref": "refs/heads/main",
        "repository": copy.deepcopy(repository),
        "head_repository": copy.deepcopy(repository),
    }
    publication_artifact = {
        "id": 8401,
        "name": (
            f"trusted-image-publication-{TRUSTED_CI_RUN_ID}"
            f"-attempt-{TRUSTED_CI_RUN_ATTEMPT}"
        ),
        "expired": False,
        "workflow_run": {
            "id": TRUSTED_CI_RUN_ID,
            "repository_id": TRUSTED_REPOSITORY_ID,
            "head_repository_id": TRUSTED_REPOSITORY_ID,
            "head_branch": "main",
            "head_sha": TRUSTED_TARGET_SHA,
        },
    }
    workflows = {
        ".github/workflows/deploy-staging.yml": {
            "id": TRUSTED_REQUEST_WORKFLOW_ID,
            "path": ".github/workflows/deploy-staging.yml",
            "name": "deploy-staging",
        },
        TRUSTED_REQUEST_WORKFLOW_ID: {
            "id": TRUSTED_REQUEST_WORKFLOW_ID,
            "path": ".github/workflows/deploy-staging.yml",
            "name": "deploy-staging",
        },
        ".github/workflows/ci.yml": {
            "id": TRUSTED_CI_WORKFLOW_ID,
            "path": ".github/workflows/ci.yml",
            "name": "ci",
        },
        TRUSTED_CI_WORKFLOW_ID: {
            "id": TRUSTED_CI_WORKFLOW_ID,
            "path": ".github/workflows/ci.yml",
            "name": "ci",
        },
    }

    class FakeApi:
        def __init__(self):
            self.run = copy.deepcopy(request_run)
            self.artifact = copy.deepcopy(artifact)
            self.workflows = copy.deepcopy(workflows)
            self.ci_run = copy.deepcopy(ci_run)
            self.publication_artifact = copy.deepcopy(publication_artifact)
            self.jobs = [
                {
                    "name": "build / push GHCR images",
                    "run_id": TRUSTED_CI_RUN_ID,
                    "workflow_name": "ci",
                    "workflow_id": TRUSTED_CI_WORKFLOW_ID,
                    "path": ".github/workflows/ci.yml",
                    "head_sha": TRUSTED_TARGET_SHA,
                    "head_branch": "main",
                    "status": "completed",
                    "conclusion": "success",
                }
            ]

        def repository(self, repository_name):
            assert repository_name == TRUSTED_REPOSITORY
            return {**repository, "default_branch": "main"}

        def workflow_run(self, repository_name, run_id):
            assert repository_name == TRUSTED_REPOSITORY
            assert run_id == TRUSTED_REQUEST_RUN_ID
            return copy.deepcopy(self.run)

        def workflow_by_path(self, repository_name, path):
            assert repository_name == TRUSTED_REPOSITORY
            return copy.deepcopy(self.workflows[path])

        def workflow_by_id(self, repository_name, workflow_id):
            assert repository_name == TRUSTED_REPOSITORY
            return copy.deepcopy(self.workflows[workflow_id])

        def workflow_run_artifacts(self, repository_name, run_id):
            assert repository_name == TRUSTED_REPOSITORY
            if run_id == TRUSTED_REQUEST_RUN_ID:
                return {"artifacts": [copy.deepcopy(self.artifact)]}
            assert run_id == TRUSTED_CI_RUN_ID
            return {"artifacts": [copy.deepcopy(self.publication_artifact)]}

        def artifact_zip(self, repository_name, artifact_id):
            assert repository_name == TRUSTED_REPOSITORY
            if artifact_id == self.artifact["id"]:
                return _trusted_request_zip(request)
            assert artifact_id == self.publication_artifact["id"]
            return _trusted_request_zip(
                _trusted_image_publication(), member_name="trusted-image-publication.json"
            )

        def workflow_runs(self, repository_name, workflow_id, head_sha):
            assert repository_name == TRUSTED_REPOSITORY
            assert workflow_id == TRUSTED_CI_WORKFLOW_ID
            assert head_sha == TRUSTED_TARGET_SHA
            return {"workflow_runs": [copy.deepcopy(self.ci_run)]}

        def workflow_run_jobs(self, repository_name, run_id):
            assert repository_name == TRUSTED_REPOSITORY
            assert run_id == TRUSTED_CI_RUN_ID
            return {"jobs": copy.deepcopy(self.jobs)}

    return event, _trusted_workflow_allowlist(), FakeApi()


def test_trusted_verify_workflow_is_workflow_run_only_and_read_only():
    workflow_path = REPOSITORY_ROOT / ".github/workflows/trusted-deploy.yml"
    workflow = _load_workflow(workflow_path)
    assert workflow["on"]["workflow_run"]["types"] == ["completed"]
    assert workflow["on"]["workflow_run"]["workflows"] == [
        "deploy-staging",
        "deploy-prod",
        "rollback",
    ]
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    job = workflow["jobs"]["verify"]
    assert "environment" not in job
    source = workflow_path.read_text(encoding="utf-8")
    assert "workflow_dispatch" not in source
    assert "secrets." not in source
    assert "ssh " not in source
    assert "docker login" not in source
    checkout = job["steps"][0]
    assert checkout["uses"] == "actions/checkout@v4"
    assert checkout["with"] == {
        "ref": "refs/heads/main",
        "persist-credentials": False,
        "fetch-depth": 1,
    }


def test_trusted_workflow_id_allowlist_fails_closed_when_ids_are_unregistered(tmp_path):
    allowlist_path = tmp_path / "trusted-workflow-ids.json"
    allowlist_path.write_text(
        json.dumps(_trusted_workflow_allowlist(request_workflow_id=None, ci_workflow_id=None)),
        encoding="utf-8",
    )
    allowlist = trusted_workflow_run_validator.load_allowlist(allowlist_path)
    event, _, api = _trusted_workflow_run_fixture()
    with pytest.raises(
        trusted_workflow_run_validator.ProvenanceValidationError,
        match="request workflow.id is not registered",
    ):
        trusted_workflow_run_validator.validate_provenance(
            event=event,
            allowlist=allowlist,
            expected_repository=TRUSTED_REPOSITORY,
            expected_repository_id=TRUSTED_REPOSITORY_ID,
            orchestrator_ref="refs/heads/main",
            api=api,
        )


def test_trusted_provenance_accepts_bound_request_and_ci_publication():
    event, allowlist, api = _trusted_workflow_run_fixture()
    result = trusted_workflow_run_validator.validate_provenance(
        event=event,
        allowlist=allowlist,
        expected_repository=TRUSTED_REPOSITORY,
        expected_repository_id=TRUSTED_REPOSITORY_ID,
        orchestrator_ref="refs/heads/main",
        api=api,
    )
    assert result == {
        "verified": True,
        "request_type": "deploy",
        "environment": "staging",
        "image_tag": "sha-aaaaaaa",
        "canonical_image_tag": f"sha-{TRUSTED_TARGET_SHA}",
        "deploy_sha": TRUSTED_TARGET_SHA,
        "request_run_id": TRUSTED_REQUEST_RUN_ID,
        "artifact_id": 8301,
        "ci_run_id": TRUSTED_CI_RUN_ID,
        "ci_run_attempt": TRUSTED_CI_RUN_ATTEMPT,
        "publication_artifact_id": 8401,
        "web_image_repository": "ghcr.io/example/project/ai-reader-web",
        "web_image_digest": PUBLICATION_DIGESTS["web"],
        "api_image_repository": "ghcr.io/example/project/ai-reader-api",
        "api_image_digest": PUBLICATION_DIGESTS["api"],
        "worker_image_repository": "ghcr.io/example/project/ai-reader-worker",
        "worker_image_digest": PUBLICATION_DIGESTS["worker"],
    }


def test_trusted_provenance_allows_event_payload_without_optional_path():
    event, allowlist, api = _trusted_workflow_run_fixture()
    del event["workflow_run"]["path"]
    result = trusted_workflow_run_validator.validate_provenance(
        event=event,
        allowlist=allowlist,
        expected_repository=TRUSTED_REPOSITORY,
        expected_repository_id=TRUSTED_REPOSITORY_ID,
        orchestrator_ref="refs/heads/main",
        api=api,
    )
    assert result["verified"] is True


def test_trusted_provenance_writes_canonical_image_and_digest_outputs(tmp_path):
    event, allowlist, api = _trusted_workflow_run_fixture()
    result = trusted_workflow_run_validator.validate_provenance(
        event=event,
        allowlist=allowlist,
        expected_repository=TRUSTED_REPOSITORY,
        expected_repository_id=TRUSTED_REPOSITORY_ID,
        orchestrator_ref="refs/heads/main",
        api=api,
    )
    output_path = tmp_path / "github-output"
    trusted_workflow_run_validator._write_outputs(output_path, result)
    outputs = dict(
        line.split("=", 1) for line in output_path.read_text(encoding="utf-8").splitlines()
    )
    assert outputs["deploy_sha"] == TRUSTED_TARGET_SHA
    assert outputs["canonical_image_tag"] == f"sha-{TRUSTED_TARGET_SHA}"
    assert outputs["ci_run_attempt"] == str(TRUSTED_CI_RUN_ATTEMPT)
    for image_name in ("web", "api", "worker"):
        assert outputs[f"{image_name}_image_repository"] == (
            f"ghcr.io/example/project/ai-reader-{image_name}"
        )
        assert outputs[f"{image_name}_image_digest"] == PUBLICATION_DIGESTS[image_name]


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("fork", "run.repository.id mismatch"),
        ("workflow-id", "run.workflow_id mismatch"),
        ("artifact-run", "artifact.workflow_run.id mismatch"),
        ("artifact-head-repository", "artifact.workflow_run.head_repository_id mismatch"),
        ("ci-workflow", "ci workflow by path.id mismatch"),
        ("ci-job", "ci publication run must contain exactly one GHCR publication job"),
    ),
)
def test_trusted_provenance_rejects_identity_and_publication_mismatches(mutation, message):
    event, allowlist, api = _trusted_workflow_run_fixture()
    if mutation == "fork":
        api.run["repository"]["id"] = TRUSTED_REPOSITORY_ID + 1
    elif mutation == "workflow-id":
        api.run["workflow_id"] = TRUSTED_REQUEST_WORKFLOW_ID + 1
    elif mutation == "artifact-run":
        api.artifact["workflow_run"]["id"] = TRUSTED_REQUEST_RUN_ID + 1
    elif mutation == "artifact-head-repository":
        api.artifact["workflow_run"]["head_repository_id"] = TRUSTED_REPOSITORY_ID + 1
    elif mutation == "ci-workflow":
        api.workflows[".github/workflows/ci.yml"]["id"] = TRUSTED_CI_WORKFLOW_ID + 1
    elif mutation == "ci-job":
        api.jobs = []
    with pytest.raises(trusted_workflow_run_validator.ProvenanceValidationError, match=message):
        trusted_workflow_run_validator.validate_provenance(
            event=event,
            allowlist=allowlist,
            expected_repository=TRUSTED_REPOSITORY,
            expected_repository_id=TRUSTED_REPOSITORY_ID,
            orchestrator_ref="refs/heads/main",
            api=api,
        )


def _trusted_request_variant(
    workflow_name: str, request_type: str, environment: str
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    event, allowlist, api = _trusted_workflow_run_fixture()
    workflow_path = f".github/workflows/{workflow_name}.yml"
    artifact_name = (
        "trusted-staging-deploy-request"
        if workflow_name == "deploy-staging"
        else "trusted-production-deploy-request"
        if workflow_name == "deploy-prod"
        else "trusted-rollback-request"
    )
    request = _valid_trusted_request(request_type=request_type, environment=environment)
    api.run.update({"path": workflow_path, "name": workflow_name})
    event["workflow_run"].update({"path": workflow_path, "name": workflow_name})
    api.artifact.update(
        {
            "name": artifact_name,
            "workflow_run": {
                "id": TRUSTED_REQUEST_RUN_ID,
                "repository_id": TRUSTED_REPOSITORY_ID,
                "head_repository_id": TRUSTED_REPOSITORY_ID,
                "head_branch": "main",
                "head_sha": TRUSTED_REQUEST_HEAD_SHA,
            },
        }
    )
    request_workflow = {
        "id": TRUSTED_REQUEST_WORKFLOW_ID,
        "path": workflow_path,
        "name": workflow_name,
    }
    api.workflows = {
        workflow_path: copy.deepcopy(request_workflow),
        TRUSTED_REQUEST_WORKFLOW_ID: copy.deepcopy(request_workflow),
        ".github/workflows/ci.yml": {
            "id": TRUSTED_CI_WORKFLOW_ID,
            "path": ".github/workflows/ci.yml",
            "name": "ci",
        },
        TRUSTED_CI_WORKFLOW_ID: {
            "id": TRUSTED_CI_WORKFLOW_ID,
            "path": ".github/workflows/ci.yml",
            "name": "ci",
        },
    }
    def artifact_zip(repository_name, artifact_id):
        assert repository_name == TRUSTED_REPOSITORY
        if artifact_id == api.artifact["id"]:
            return _trusted_request_zip(
                request,
                member_name=(
                    "trusted-rollback-request.json"
                    if request_type == "rollback"
                    else "trusted-deploy-request.json"
                ),
            )
        assert artifact_id == api.publication_artifact["id"]
        return _trusted_request_zip(
            _trusted_image_publication(), member_name="trusted-image-publication.json"
        )

    api.artifact_zip = artifact_zip
    return event, allowlist, api


@pytest.mark.parametrize(
    ("workflow_name", "request_type", "environment"),
    (
        ("deploy-staging", "deploy", "staging"),
        ("deploy-prod", "deploy", "prod"),
        ("rollback", "rollback", "staging"),
        ("rollback", "rollback", "prod"),
    ),
)
def test_trusted_provenance_accepts_all_fixed_request_mappings(
    workflow_name, request_type, environment
):
    event, allowlist, api = _trusted_request_variant(workflow_name, request_type, environment)
    result = trusted_workflow_run_validator.validate_provenance(
        event=event,
        allowlist=allowlist,
        expected_repository=TRUSTED_REPOSITORY,
        expected_repository_id=TRUSTED_REPOSITORY_ID,
        orchestrator_ref="refs/heads/main",
        api=api,
    )
    assert result["request_type"] == request_type
    assert result["environment"] == environment


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("wrong-ref", "workflow_run.ref mismatch"),
        ("wrong-event", "workflow_run.event mismatch"),
        ("non-completed", "workflow_run.status mismatch"),
        ("failed-request", "workflow_run.conclusion mismatch"),
        ("fork-head", "run.head_repository.id mismatch"),
        ("expired-artifact", "request artifact must not be expired"),
        ("duplicate-artifact", "workflow run artifacts do not match"),
        ("artifact-branch", "artifact head branch mismatch"),
        ("artifact-sha", "artifact head SHA mismatch"),
        ("bad-request-schema", "request artifact failed schema validation"),
        ("ci-pr", "no successful canonical main ci publication run"),
        ("ci-failed", "no successful canonical main ci publication run"),
        ("ci-job-run", "ci image job workflow run ID mismatch"),
        ("ci-job-sha", "ci image job head SHA mismatch"),
        ("ci-job-status", "ci image job status mismatch"),
    ),
)
def test_trusted_provenance_rejects_provenance_and_publication_failures(mutation, message):
    event, allowlist, api = _trusted_workflow_run_fixture()
    if mutation == "wrong-ref":
        event["workflow_run"]["ref"] = "refs/heads/attacker"
    elif mutation == "wrong-event":
        event["workflow_run"]["event"] = "pull_request"
    elif mutation == "non-completed":
        event["workflow_run"]["status"] = "in_progress"
    elif mutation == "failed-request":
        event["workflow_run"]["conclusion"] = "failure"
    elif mutation == "fork-head":
        api.run["head_repository"]["id"] = TRUSTED_REPOSITORY_ID + 1
    elif mutation == "expired-artifact":
        api.artifact["expired"] = True
    elif mutation == "duplicate-artifact":
        api.workflow_run_artifacts = lambda *_: {
            "artifacts": [copy.deepcopy(api.artifact), copy.deepcopy(api.artifact)]
        }
    elif mutation == "artifact-branch":
        api.artifact["workflow_run"]["head_branch"] = "attacker"
    elif mutation == "artifact-sha":
        api.artifact["workflow_run"]["head_sha"] = "c" * 40
    elif mutation == "bad-request-schema":
        api.artifact_zip = lambda *_: _trusted_request_zip(
            {**_valid_trusted_request(), "unexpected": "field"}
        )
    elif mutation == "ci-pr":
        api.ci_run["event"] = "pull_request"
    elif mutation == "ci-failed":
        api.ci_run["conclusion"] = "failure"
    elif mutation == "ci-job-run":
        api.jobs[0]["run_id"] = TRUSTED_CI_RUN_ID + 1
    elif mutation == "ci-job-sha":
        api.jobs[0]["head_sha"] = "c" * 40
    elif mutation == "ci-job-status":
        api.jobs[0]["status"] = "in_progress"
    with pytest.raises(trusted_workflow_run_validator.ProvenanceValidationError, match=message):
        trusted_workflow_run_validator.validate_provenance(
            event=event,
            allowlist=allowlist,
            expected_repository=TRUSTED_REPOSITORY,
            expected_repository_id=TRUSTED_REPOSITORY_ID,
            orchestrator_ref="refs/heads/main",
            api=api,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("expired", "ci publication artifact must not be expired"),
        ("wrong-artifact-run", "publication artifact.workflow_run.id mismatch"),
        (
            "duplicate",
            "ci publication artifacts do not contain exactly one expected publication artifact",
        ),
        (
            "different-attempt-artifact",
            "ci publication artifacts do not contain exactly one expected publication artifact",
        ),
        ("workflow", "publication.workflow_id mismatch"),
        ("run", "publication.run_id mismatch"),
        ("attempt", "publication.run_attempt mismatch"),
        ("sha", "publication.deploy_sha mismatch"),
        ("tag", "ci publication artifact failed schema validation"),
        ("digest", "ci publication artifact failed schema validation"),
    ),
)
def test_trusted_provenance_rejects_unbound_or_unsafe_ci_publication(
    mutation, message
):
    event, allowlist, api = _trusted_workflow_run_fixture()
    if mutation == "expired":
        api.publication_artifact["expired"] = True
    elif mutation == "wrong-artifact-run":
        api.publication_artifact["workflow_run"]["id"] = TRUSTED_CI_RUN_ID + 1
    elif mutation == "duplicate":
        original_artifacts = api.workflow_run_artifacts
        api.workflow_run_artifacts = lambda repository_name, run_id: (
            {
                "artifacts": [
                    copy.deepcopy(api.publication_artifact),
                    copy.deepcopy(api.publication_artifact),
                ]
            }
            if run_id == TRUSTED_CI_RUN_ID
            else original_artifacts(repository_name, run_id)
        )
    elif mutation == "different-attempt-artifact":
        api.publication_artifact["name"] = (
            f"trusted-image-publication-{TRUSTED_CI_RUN_ID}"
            f"-attempt-{TRUSTED_CI_RUN_ATTEMPT + 1}"
        )
    else:
        publication = _trusted_image_publication()
        if mutation == "workflow":
            publication["workflow_id"] = str(TRUSTED_CI_WORKFLOW_ID + 1)
        elif mutation == "run":
            publication["run_id"] = str(TRUSTED_CI_RUN_ID + 1)
        elif mutation == "attempt":
            publication["run_attempt"] = str(TRUSTED_CI_RUN_ATTEMPT + 1)
        elif mutation == "sha":
            publication["deploy_sha"] = "b" * 40
            publication["image_tag"] = f"sha-{'b' * 40}"
        elif mutation == "tag":
            publication["image_tag"] = f"sha-{'b' * 40}"
        elif mutation == "digest":
            publication["images"]["worker"]["digest"] = f"sha256:{'B' * 64}"
        else:
            raise AssertionError(f"unhandled mutation: {mutation}")
        original_artifact_zip = api.artifact_zip
        api.artifact_zip = lambda repository_name, artifact_id: (
            _trusted_request_zip(
                publication, member_name="trusted-image-publication.json"
            )
            if artifact_id == api.publication_artifact["id"]
            else original_artifact_zip(repository_name, artifact_id)
        )

    with pytest.raises(trusted_workflow_run_validator.ProvenanceValidationError, match=message):
        trusted_workflow_run_validator.validate_provenance(
            event=event,
            allowlist=allowlist,
            expected_repository=TRUSTED_REPOSITORY,
            expected_repository_id=TRUSTED_REPOSITORY_ID,
            orchestrator_ref="refs/heads/main",
            api=api,
        )


def test_postgres_performance_artifacts_separate_main_baseline_from_pr_candidate():
    workflow = _load_workflow(CI_WORKFLOW)
    steps = workflow["jobs"]["checks"]["steps"]
    baseline = next(step for step in steps if step.get("name") == "Upload canonical-main PostgreSQL performance baseline")
    candidate = next(step for step in steps if step.get("name") == "Upload PR PostgreSQL performance candidate")

    assert baseline["uses"] == "actions/upload-artifact@v4"
    assert baseline["with"] == {
        "name": "db-postgres-performance-baseline-main",
        "path": "output/performance/db-postgres-ci.json",
        "if-no-files-found": "error",
        "retention-days": 90,
    }
    assert "github.event_name == 'push'" in baseline["if"]
    assert "github.ref == 'refs/heads/main'" in baseline["if"]
    assert "github.repository == 'blankhoney/reno_rss'" in baseline["if"]
    assert candidate["with"]["name"] == "db-postgres-performance-candidate"
    assert candidate["with"]["retention-days"] == 14
    assert candidate["if"] == "${{ github.event_name == 'pull_request' && !cancelled() }}"


def test_postgres_performance_resolver_replaces_run_only_download_selector():
    workflow = _load_workflow(CI_WORKFLOW)
    steps = workflow["jobs"]["checks"]["steps"]
    resolver_step = next(
        step for step in steps if step.get("name") == "Resolve trusted canonical-main PostgreSQL baseline"
    )
    compare = next(step for step in steps if step.get("name") == "Compare PostgreSQL performance baseline")
    source = _workflow_source()

    assert resolver_step["env"] == {
        "GITHUB_TOKEN": "${{ github.token }}",
        "GITHUB_API_URL": "${{ github.api_url }}",
    }
    command = resolver_step["run"]
    assert ".github/scripts/resolve-performance-baseline.py" in command
    assert "--repository \"$GITHUB_REPOSITORY\"" in command
    assert "--repository-id \"$GITHUB_REPOSITORY_ID\"" in command
    assert "--trust-config .github/scripts/trusted-workflow-ids.json" in command
    assert "--artifact-name db-postgres-performance-baseline-main" in command
    assert "--github-output \"$GITHUB_OUTPUT\"" in command
    assert "actions/download-artifact" not in source
    assert "per_page: 1" not in source
    assert compare["if"] == "${{ steps.performance_baseline.outputs.mode == 'comparison' }}"
    assert "--max-regression 3" in compare["run"]


def test_postgres_performance_producer_receives_attempt_scoped_identity():
    workflow = _load_workflow(CI_WORKFLOW)
    producer_step = next(
        step
        for step in workflow["jobs"]["checks"]["steps"]
        if step.get("name") == "Run PostgreSQL performance baseline"
    )
    assert producer_step["env"] == {
        "DB_PERF_DATABASE_URL": "postgres://postgres:postgres@localhost:5432/postgres",
        "GITHUB_RUN_ID": "${{ github.run_id }}",
        "GITHUB_RUN_ATTEMPT": "${{ github.run_attempt }}",
        "GITHUB_SHA": "${{ github.sha }}",
    }


def test_postgres_comparison_and_bootstrap_outputs_cannot_be_confused():
    workflow = _load_workflow(CI_WORKFLOW)
    steps = workflow["jobs"]["checks"]["steps"]
    comparison = next(step for step in steps if step.get("name") == "Upload PostgreSQL performance comparison")
    bootstrap = next(step for step in steps if step.get("name") == "Upload PostgreSQL performance bootstrap status")
    summary = next(step for step in steps if step.get("name") == "Summarize PostgreSQL performance baseline")

    assert comparison["if"] == "${{ steps.performance_baseline.outputs.mode == 'comparison' && !cancelled() }}"
    assert comparison["with"]["retention-days"] == 90
    assert "db-postgres-comparison.json" in comparison["with"]["path"]
    assert "provenance.json" in comparison["with"]["path"]
    assert bootstrap["if"] == "${{ steps.performance_baseline.outputs.mode == 'bootstrap' && !cancelled() }}"
    assert bootstrap["with"]["name"] == "db-postgres-performance-bootstrap-status"
    assert bootstrap["with"]["path"] == "output/performance/main-baseline/provenance.json"
    assert "no regression comparison was possible" in summary["run"]


def test_performance_freshness_workflow_is_read_only_and_uses_expires_at_resolver():
    path = REPOSITORY_ROOT / ".github/workflows/performance-baseline-freshness.yml"
    workflow = _load_workflow(path)
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    assert "schedule" in workflow["on"]
    steps = workflow["jobs"]["freshness"]["steps"]
    checkout = steps[0]
    assert checkout["uses"] == "actions/checkout@v4"
    assert checkout["with"] == {
        "ref": "refs/heads/main",
        "persist-credentials": False,
        "fetch-depth": 1,
    }
    command = steps[1]["run"]
    assert "--freshness-threshold-days 14" in command
    source = path.read_text(encoding="utf-8")
    assert "upload-artifact" not in source
    assert "download-artifact" not in source
    assert "issues: write" not in source
    assert "actions: write" not in source
    assert "contents: write" not in source


def test_checked_in_trust_config_registers_canonical_workflow_ids():
    trust = json.loads(
        (REPOSITORY_ROOT / ".github/scripts/trusted-workflow-ids.json").read_text(encoding="utf-8")
    )
    assert {
        key: {field: config[field] for field in ("path", "name", "id")}
        for key, config in trust["request_workflows"].items()
    } == {
        "deploy-staging": {
            "path": ".github/workflows/deploy-staging.yml",
            "name": "deploy-staging",
            "id": 274785175,
        },
        "deploy-prod": {
            "path": ".github/workflows/deploy-prod.yml",
            "name": "deploy-prod",
            "id": 274785174,
        },
        "rollback": {
            "path": ".github/workflows/rollback.yml",
            "name": "rollback",
            "id": 274785177,
        },
    }
    assert trust["ci_workflow"] == {
        "path": ".github/workflows/ci.yml",
        "name": "ci",
        "id": 274785172,
    }
    resolver_source = (
        REPOSITORY_ROOT / ".github/scripts/resolve-performance-baseline.py"
    ).read_text(encoding="utf-8")
    assert "trust config ci_workflow.id is not registered" in resolver_source

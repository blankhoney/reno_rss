"""Static regression locks for the GitHub Actions CI delivery boundary."""

import copy
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
from typing import Any
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/ci.yml"


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


def test_pr_runs_checks_only_and_ci_never_mutates_the_vps():
    source = _workflow_source()

    assert _job_condition(source, "images") == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    )
    assert "deploy-staging:" not in source
    assert "ssh " not in source
    assert "VPS_SSH_KEY" not in source
    assert "github.event.pull_request.head.repo.full_name == github.repository" not in _job_block(
        source, "images"
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

    assert _paths_ignore_entries(source, "pull_request") == ["PLANS.md"]
    assert _paths_ignore_entries(source, "push") == ["PLANS.md"]
    assert "docs/**" not in source


def test_release_record_commit_cannot_be_excluded_from_canonical_ci():
    source = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "docs/**" not in source
    assert "docs/releases" not in _paths_ignore_entries(source, "push")
    assert "**/*.md" not in source


def test_playwright_matrix_install_is_bounded_diagnostic_and_complete():
    workflow = _load_workflow(CI_WORKFLOW)
    steps = workflow["jobs"]["checks"]["steps"]
    dependencies = next(step for step in steps if step.get("name") == "Install Playwright system dependencies")
    browsers = next(step for step in steps if step.get("name") == "Install Playwright browser matrix")
    assert dependencies["timeout-minutes"] == 10
    assert dependencies["run"] == "npx playwright install-deps chromium firefox webkit"
    assert browsers["timeout-minutes"] == 20
    assert browsers["env"]["PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT"] == "120000"
    assert "timeout --signal=TERM --kill-after=30s 8m" in browsers["run"]
    assert "npx playwright install chromium firefox webkit" in browsers["run"]
    assert "for attempt in 1 2" in browsers["run"]
    assert "exit 1" in browsers["run"]


def test_shared_contract_linux_fixtures_are_prepared_bounded_and_serial():
    workflow = _load_workflow(CI_WORKFLOW)
    steps = workflow["jobs"]["checks"]["steps"]
    prepare = next(
        step for step in steps if step.get("name") == "Prepare shared-contract Linux fixture image"
    )
    contract = next(step for step in steps if step.get("name") == "Test shared VPS contract")
    assert prepare["timeout-minutes"] == 6
    assert prepare["run"] == (
        "timeout --signal=TERM --kill-after=30s 5m docker pull node:22-bookworm"
    )
    assert contract["timeout-minutes"] == 15
    assert "for test_file in" in contract["run"]
    assert "Running bounded shared-contract fixture" in contract["run"]
    assert "timeout --signal=TERM --kill-after=10s 2m" in contract["run"]
    assert "node --test --test-concurrency=1" in contract["run"]
    assert "shared-release-lock.test.mjs" in contract["run"]
    assert "shared-release-bootstrap.test.mjs" in contract["run"]
    assert "trusted-remote-transaction.test.mjs" in contract["run"]


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
        if workflow_path.name == "deploy-prod.yml":
            expected_inputs.update(
                {"staging_receipt_run", "rollback_receipt_run", "forward_receipt_run", "rollback_target_sha", "release_record_ref", "release_record_digest", "control_plane_sha"}
            )
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
        expected_env = {"REQUEST_TYPE", "DEPLOY_ENV", "IMAGE_TAG", "DEPLOY_SHA"}
        if workflow_path.name == "deploy-prod.yml":
            expected_env.update(
                {"STAGING_RECEIPT_RUN", "ROLLBACK_RECEIPT_RUN", "FORWARD_RECEIPT_RUN", "ROLLBACK_TARGET_SHA", "RELEASE_RECORD_REF", "RELEASE_RECORD_DIGEST", "CONTROL_PLANE_SHA"}
            )
        assert set(validation["env"]) == expected_env
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
        assert '[[ "$IMAGE_TAG" =~ ^sha-[0-9a-f]{40}$ ]]' in run_block
        assert 'expected_tag="sha-${DEPLOY_SHA}"' in run_block
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
        expected_uses = [None, "actions/upload-artifact@v4"]
        if workflow_path.name == "deploy-prod.yml":
            expected_uses.append("actions/upload-artifact@v4")
        assert [step.get("uses") for step in job["steps"]] == expected_uses
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
        expected_steps = [
            "Validate request inputs",
            "Upload trusted deploy request"
            if workflow_path.name != "rollback.yml"
            else "Upload trusted rollback request",
        ]
        if workflow_path.name == "deploy-prod.yml":
            expected_steps.append("Upload trusted production promotion proof")
        assert [step["name"] for step in job["steps"]] == expected_steps


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
        "image_tag": f"sha-{deploy_sha}",
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
            "image_tag must use the sha-<40 lowercase hexadecimal> format",
        ),
        (
            "mismatch",
            {**_valid_trusted_request(), "deploy_sha": "b" * 40},
            "image_tag must equal deploy_sha",
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


def test_ci_publishes_full_sha_and_never_executes_a_deployment():
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
    assert "deploy-staging" not in workflow["jobs"]


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


def _promotion_receipt(
    phase: str, operation_sha: str, workflow_run: int, pre_runtime_sha: str
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "contractVersion": 1,
        "owner": {"project": "rss", "repo": "blankhoney/reno_rss"},
        "operation": {"fullSha": operation_sha},
        "workflowRun": workflow_run,
        "phase": phase,
        "runtime": {
            "fullSha": operation_sha if phase == "post-activation" else pre_runtime_sha
        },
        "rollback": {"rollbackFrom": None, "target": None},
        "timestamp": "2026-08-20T00:00:00Z",
        "overallStatus": "success",
        "urls": [
            {"name": "blog-public", "configuredURL": "https://blog.blankhoney.xyz/zh",
             "status": 200, "finalURL": "https://blog.blankhoney.xyz/zh", "tls": True,
             "redirect": False, "result": "success", "error": None},
            {"name": "blog-public-status", "configuredURL": "https://blog.blankhoney.xyz/api/status",
             "status": 200, "finalURL": "https://blog.blankhoney.xyz/api/status", "tls": True,
             "redirect": False, "result": "success", "error": None},
            {"name": "rss-production-auth", "configuredURL": "https://ai-reader.blankhoney.xyz/",
             "status": 200, "finalURL": "https://auth.blankhoney.xyz/", "tls": True,
             "redirect": True, "result": "success", "error": None},
        ],
        "edge": {
            "caddyContainer": "myrss-edge-caddy-1", "myrssAppAttached": True,
            "brianstormEdgeAttached": True, "networkDriver": "bridge",
            "configLoaded": True, "rssUpstreamReachable": True, "blogUpstreamReachable": True,
            "result": "success", "error": None,
        },
    }
    if phase in {"post-rollback", "post-compensation"}:
        receipt["rollback"] = {
            "rollbackFrom": pre_runtime_sha,
            "target": operation_sha,
        }
        receipt["runtime"] = {
            "fullSha": operation_sha if phase == "post-rollback" else pre_runtime_sha
        }
    return receipt


def _promotion_receipt_zip(
    operation_sha: str,
    workflow_run: int,
    *,
    pre_runtime_sha: str,
    rollback: bool = False,
) -> bytes:
    phases = (
        ("pre-mutation", "pre-activation", "post-rollback")
        if rollback
        else ("pre-mutation", "pre-activation", "post-activation")
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for phase in phases:
            archive.writestr(
                f"{phase}.json",
                json.dumps(
                    _promotion_receipt(
                        phase, operation_sha, workflow_run, pre_runtime_sha
                    )
                ),
            )
    return output.getvalue()


def _production_release_record(
    *,
    operation_sha: str,
    rollback_target_sha: str,
    staging_run: int,
    rollback_run: int,
    forward_run: int,
    publication_artifact_digest: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": "rss-production-release/v1",
        "repository": TRUSTED_REPOSITORY,
        "operationSha": operation_sha,
        "canonicalCi": {
            "workflowId": TRUSTED_CI_WORKFLOW_ID,
            "runId": TRUSTED_CI_RUN_ID,
            "runAttempt": TRUSTED_CI_RUN_ATTEMPT,
            "publicationArtifactId": 8401,
            "publicationArtifactDigest": publication_artifact_digest,
            "imageTag": f"sha-{operation_sha}",
            "images": copy.deepcopy(PUBLICATION_DIGESTS),
        },
        "staging": {"workflowRun": staging_run},
        "rollback": {
            "workflowRun": rollback_run,
            "rollbackTargetSha": rollback_target_sha,
        },
        "forward": {"workflowRun": forward_run},
        "plan": {
            "backup": {
                "required": True,
                "timing": "before-compose-or-activation",
                "verification": "sha256sum",
            },
            "migration": {
                "strategy": "forward-only",
                "gate": "verified-production-backup",
            },
            "rollback": {
                "strategy": "runtime-state-guarded",
                "probe": "post-rollback-or-compensation",
            },
        },
    }


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
                "promotion_artifact": "trusted-production-promotion-proof",
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
        "digest": f"sha256:{'e' * 64}",
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

        def main_tip(self, repository_name):
            assert repository_name == TRUSTED_REPOSITORY
            return TRUSTED_TARGET_SHA

    return event, _trusted_workflow_allowlist(), FakeApi()


def test_trusted_workflow_verifies_read_only_then_executes_one_locked_transaction():
    workflow_path = REPOSITORY_ROOT / ".github/workflows/trusted-deploy.yml"
    workflow = _load_workflow(workflow_path)
    assert workflow["on"]["workflow_run"]["types"] == ["completed"]
    assert workflow["on"]["workflow_run"]["workflows"] == [
        "deploy-staging",
        "deploy-prod",
        "rollback",
    ]
    assert workflow["permissions"] == {"actions": "read", "contents": "read"}
    verify = workflow["jobs"]["verify"]
    assert "environment" not in verify
    assert verify["outputs"]["canonical_image_tag"] == (
        "${{ steps.provenance.outputs.canonical_image_tag }}"
    )
    source = workflow_path.read_text(encoding="utf-8")
    assert "workflow_dispatch" not in source
    verify_source = "\\n".join(
        step.get("run", "") for step in verify["steps"] if isinstance(step, dict)
    )
    assert "secrets." not in verify_source
    assert "ssh " not in verify_source
    assert "docker login" not in verify_source
    checkout = verify["steps"][0]
    assert checkout["uses"] == "actions/checkout@v4"
    assert checkout["with"] == {
        "ref": "refs/heads/main",
        "persist-credentials": False,
        "fetch-depth": 1,
    }
    execute = workflow["jobs"]["execute"]
    assert execute["needs"] == "verify"
    assert execute["environment"]["name"] == (
        "${{ needs.verify.outputs.environment == 'prod' && 'production' || 'staging' }}"
    )
    transaction = next(
        step for step in execute["steps"] if step.get("name") == "Execute one locked VPS transaction"
    )
    execute_env = transaction["env"]
    shared_lock_env = {
        key: value for key, value in execute_env.items() if key.startswith("SHARED_RELEASE_LOCK_")
    }
    assert shared_lock_env == {
        "SHARED_RELEASE_LOCK_WRAPPER_SHA256": "${{ vars.SHARED_RELEASE_LOCK_WRAPPER_SHA256 }}",
        "SHARED_RELEASE_LOCK_CORE_SHA256": "${{ vars.SHARED_RELEASE_LOCK_CORE_SHA256 }}",
        "SHARED_RELEASE_LOCK_TRANSACTION_SHA256": (
            "${{ vars.SHARED_RELEASE_LOCK_TRANSACTION_SHA256 }}"
        ),
    }
    assert not any(
        forbidden in execute_env
        for forbidden in (
            "SHARED_RELEASE_LOCK_ROOT",
            "SHARED_RELEASE_LOCK_PATH",
            "SHARED_RELEASE_LOCK_OWNER",
            "SHARED_RELEASE_LOCK_GROUP",
            "SHARED_RELEASE_LOCK_INHERITED_FD",
            "SHARED_RELEASE_LOCK_CORE_FD",
            "SHARED_RELEASE_LOCK_TOKEN",
        )
    )
    run = transaction["run"]
    assert "validate-known-hosts.sh" in run
    assert "ssh-keyscan" not in run
    assert ' -p "$VPS_PORT"' in run
    assert "/usr/local/lib/reno-shared-vps/release-lock-v1/with-shared-release-lock.sh" in run
    assert "trusted-remote-deploy.sh" in run
    assert "build-trusted-deploy-bundle.sh" in run
    assert '--request-type "$REQUEST_TYPE"' in run
    assert 'CONTROL_PLANE_SHA="${{ needs.verify.outputs.control_plane_sha }}"' in run
    assert '[[ "$CONTROL_PLANE_SHA" =~ ^[0-9a-f]{40}$ ]]' in run
    assert '--control-plane-sha "$CONTROL_PLANE_SHA"' in run
    assert 'tee "$ssh_stdout_file"' in run
    assert "validate-trusted-shared-edge-receipts.py" in run
    assert 'pipeline_status=("${PIPESTATUS[@]}")' in run
    assert "receipt_expect=compensation" in run
    assert 'chmod 600 "$ssh_stdout_file"' in run
    assert 'mkdir -p "$(dirname "$receipt_dir")"' in run
    assert 'remote_command="bash -c $(quote "$remote_preflight")"' in run
    assert ' "$remote_command" | tee "$ssh_stdout_file"' in run
    assert "exec 8<&0" in run
    assert "RENO_SHARED_RELEASE_BUNDLE_FD=8" in run
    assert "SHARED_RELEASE_LOCK_INHERITED_FD" not in run
    assert "SHARED_RELEASE_LOCK_ROOT" not in run
    assert "flock " not in run
    assert "scp " not in run
    assert " bash -s" not in run
    assert "/srv/brianstorm/" not in run
    assert "/var/lib/reno-shared-vps/release.lock" not in run
    upload = next(
        step for step in execute["steps"] if step.get("name") == "Upload verified shared-edge receipts"
    )
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "output/evidence/trusted-shared-edge-receipts/"
    assert upload["with"]["if-no-files-found"] == "warn"
    assert upload["with"]["retention-days"] == 30
    assert "ssh_stdout_file" not in upload["with"]["path"]


def test_trusted_workflow_binds_execution_to_verified_control_plane_sha():
    workflow_path = REPOSITORY_ROOT / ".github/workflows/trusted-deploy.yml"
    workflow = _load_workflow(workflow_path)
    verify = workflow["jobs"]["verify"]
    execute = workflow["jobs"]["execute"]
    assert verify["outputs"]["control_plane_sha"] == (
        "${{ steps.provenance.outputs.control_plane_sha }}"
    )
    checkout = execute["steps"][0]
    assert checkout["with"]["ref"] == "${{ needs.verify.outputs.control_plane_sha }}"
    run = next(
        step for step in execute["steps"] if step.get("name") == "Execute one locked VPS transaction"
    )["run"]
    assert 'CONTROL_PLANE_SHA="${{ needs.verify.outputs.control_plane_sha }}"' in run
    assert 'CONTROL_PLANE_SHA="$(git rev-parse HEAD)"' not in run
    assert '[[ "$(git rev-parse HEAD)" == "$CONTROL_PLANE_SHA" ]]' in run


def test_production_request_requires_current_sha_promotion_evidence():
    workflow = _load_workflow(REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml")
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    for name in (
        "staging_receipt_run",
        "rollback_receipt_run",
        "forward_receipt_run",
        "rollback_target_sha",
        "release_record_ref",
        "release_record_digest",
        "control_plane_sha",
    ):
        assert inputs[name]["required"] is True
    source = (REPOSITORY_ROOT / ".github/workflows/deploy-prod.yml").read_text(encoding="utf-8")
    assert "trusted-production-promotion/v1" in source
    assert "staging_receipt_run" in source
    assert "rollback_receipt_run" in source
    assert "forward_receipt_run" in source
    assert "release_record_ref" in source


def _promotion_validation_fixture() -> tuple[dict[str, Any], Any, dict[str, Any]]:
    operation = TRUSTED_TARGET_SHA
    rollback_target = "b" * 40
    control_plane = "c" * 40
    runs = {"staging": 8302, "rollback": 8303, "forward": 8304}
    artifact_ids = {8302: 8702, 8303: 8703, 8304: 8704}
    publication_digest = f"sha256:{'e' * 64}"
    record_object = _production_release_record(
        operation_sha=operation,
        rollback_target_sha=rollback_target,
        staging_run=runs["staging"],
        rollback_run=runs["rollback"],
        forward_run=runs["forward"],
        publication_artifact_digest=publication_digest,
    )

    class PromotionApi:
        def __init__(self):
            self.bad_path_run: int | None = None
            self.failed_run: int | None = None
            self.bad_archive_run: int | None = None
            self.bad_head_sha_run: int | None = None
            self.failed_control_plane_ci = False
            self.record = copy.deepcopy(record_object)

        def workflow_run(self, repository, run_id):
            assert repository == TRUSTED_REPOSITORY
            return {
                "id": run_id,
                "path": (
                    "other.yml"
                    if run_id == self.bad_path_run
                    else ".github/workflows/trusted-deploy.yml"
                ),
                "name": "trusted-deploy",
                "event": "workflow_run",
                "head_branch": "main",
                "head_sha": (
                    "not-a-full-sha" if run_id == self.bad_head_sha_run else control_plane
                ),
                "status": "completed",
                "conclusion": "failure" if run_id == self.failed_run else "success",
                "repository": _trusted_repository_identity(),
                "head_repository": _trusted_repository_identity(),
            }

        def workflow_run_artifacts(self, repository, run_id):
            expected_operation = rollback_target if run_id == runs["rollback"] else operation
            request_type = "rollback" if run_id == runs["rollback"] else "deploy"
            return {
                "artifacts": [
                    {
                        "id": artifact_ids[run_id],
                        "name": (
                            "trusted-shared-edge-receipts-staging-"
                            f"{request_type}-{run_id}-{expected_operation}"
                        ),
                        "expired": False,
                        "workflow_run": {
                            "id": run_id,
                            "head_sha": control_plane,
                        },
                    }
                ]
            }

        def workflow_runs(self, repository, workflow_id, head_sha):
            assert repository == TRUSTED_REPOSITORY
            assert workflow_id == TRUSTED_CI_WORKFLOW_ID
            assert head_sha == control_plane
            return {
                "workflow_runs": [
                    {
                        "id": 8801,
                        "workflow_id": TRUSTED_CI_WORKFLOW_ID,
                        "path": ".github/workflows/ci.yml",
                        "name": "ci",
                        "event": "push",
                        "head_branch": "main",
                        "head_sha": control_plane,
                        "status": "completed",
                        "conclusion": "failure" if self.failed_control_plane_ci else "success",
                        "repository": _trusted_repository_identity(),
                        "head_repository": _trusted_repository_identity(),
                    }
                ]
            }

        def workflow_run_jobs(self, repository, run_id):
            assert repository == TRUSTED_REPOSITORY
            assert run_id == 8801
            return {
                "jobs": [
                    {
                        "name": "build / push GHCR images",
                        "run_id": run_id,
                        "workflow_name": "ci",
                        "head_branch": "main",
                        "head_sha": control_plane,
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }

        def artifact_zip(self, repository, artifact_id):
            run_id = {value: key for key, value in artifact_ids.items()}[artifact_id]
            if run_id == self.bad_archive_run:
                return b"not-a-zip"
            if run_id == runs["rollback"]:
                return _promotion_receipt_zip(
                    rollback_target,
                    run_id,
                    pre_runtime_sha=operation,
                    rollback=True,
                )
            return _promotion_receipt_zip(
                operation,
                run_id,
                pre_runtime_sha=rollback_target,
            )

        def repository_content(self, repository, path, ref):
            assert repository == TRUSTED_REPOSITORY
            assert path == f"docs/releases/{operation}.json"
            assert ref == control_plane
            record = json.dumps(self.record, sort_keys=True).encode()
            return {"content": base64.b64encode(record).decode()}

    api = PromotionApi()
    record_bytes = json.dumps(api.record, sort_keys=True).encode()
    proof = {
        "schema_version": "trusted-production-promotion/v1",
        "operation_sha": operation,
        "control_plane_sha": control_plane,
        "rollback_target_sha": rollback_target,
        "staging_receipt": {"workflow_run": runs["staging"], "status": "success"},
        "rollback_receipt": {"workflow_run": runs["rollback"], "status": "success"},
        "forward_receipt": {"workflow_run": runs["forward"], "status": "success"},
        "release_record": {
            "ref": f"{control_plane}:docs/releases/{operation}.json",
            "digest": f"sha256:{hashlib.sha256(record_bytes).hexdigest()}",
            "provenance": True,
        },
    }
    kwargs = {
        "operation_sha": operation,
        "control_plane_sha": control_plane,
        "publication": _trusted_image_publication(),
        "publication_run_id": TRUSTED_CI_RUN_ID,
        "publication_run_attempt": TRUSTED_CI_RUN_ATTEMPT,
        "publication_artifact_id": 8401,
        "publication_artifact_digest": publication_digest,
        "ci_workflow_id": TRUSTED_CI_WORKFLOW_ID,
        "ci_workflow_path": ".github/workflows/ci.yml",
        "ci_workflow_name": "ci",
        "repository_id": TRUSTED_REPOSITORY_ID,
        "api": api,
        "repository": TRUSTED_REPOSITORY,
    }
    return proof, api, kwargs


def _promotion_proof_zip(proof: dict[str, Any], *, extra_member: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("trusted-production-promotion-proof.json", json.dumps(proof))
        if extra_member:
            archive.writestr("unexpected.json", "{}")
    return output.getvalue()


def test_production_promotion_validator_accepts_real_receipts_and_record():
    proof, _, kwargs = _promotion_validation_fixture()
    result = trusted_workflow_run_validator._promotion_proof(
        _promotion_proof_zip(proof), **kwargs
    )
    assert result["operation_sha"] == TRUSTED_TARGET_SHA


@pytest.mark.parametrize(
    "mutation",
    (
        "duplicate-run",
        "path",
        "conclusion",
        "receipt",
        "receipt-runtime",
        "record-digest",
        "record-ci",
        "record-plan",
        "record-self-reference",
        "record-ref",
        "receipt-head-sha",
        "receipt-control-plane-ci",
        "extra-proof-member",
    ),
)
def test_production_promotion_validator_rejects_tampered_evidence(mutation):
    proof, api, kwargs = _promotion_validation_fixture()
    extra_member = False
    if mutation == "duplicate-run":
        proof["forward_receipt"]["workflow_run"] = proof["staging_receipt"]["workflow_run"]
    elif mutation == "path":
        api.bad_path_run = proof["staging_receipt"]["workflow_run"]
    elif mutation == "conclusion":
        api.failed_run = proof["rollback_receipt"]["workflow_run"]
    elif mutation == "receipt-head-sha":
        api.bad_head_sha_run = proof["staging_receipt"]["workflow_run"]
    elif mutation == "receipt-control-plane-ci":
        api.failed_control_plane_ci = True
    elif mutation == "receipt":
        api.bad_archive_run = proof["forward_receipt"]["workflow_run"]
    elif mutation == "receipt-runtime":
        original = api.artifact_zip

        def bad_receipt(repository, artifact_id):
            if artifact_id == 8704:
                return _promotion_receipt_zip(
                    TRUSTED_TARGET_SHA,
                    8304,
                    pre_runtime_sha="d" * 40,
                )
            return original(repository, artifact_id)

        api.artifact_zip = bad_receipt
    elif mutation == "record-digest":
        proof["release_record"]["digest"] = f"sha256:{'0' * 64}"
    elif mutation == "record-ci":
        api.record["canonicalCi"]["runId"] += 1
        record_bytes = json.dumps(api.record, sort_keys=True).encode()
        proof["release_record"]["digest"] = f"sha256:{hashlib.sha256(record_bytes).hexdigest()}"
    elif mutation == "record-plan":
        api.record["plan"]["backup"]["required"] = False
        record_bytes = json.dumps(api.record, sort_keys=True).encode()
        proof["release_record"]["digest"] = f"sha256:{hashlib.sha256(record_bytes).hexdigest()}"
    elif mutation == "record-self-reference":
        api.record["controlPlaneSha"] = "c" * 40
        record_bytes = json.dumps(api.record, sort_keys=True).encode()
        proof["release_record"]["digest"] = f"sha256:{hashlib.sha256(record_bytes).hexdigest()}"
    elif mutation == "record-ref":
        proof["release_record"]["ref"] = (
            f"{'c' * 40}:docs/releases/not-the-candidate.json"
        )
    elif mutation == "extra-proof-member":
        extra_member = True
    with pytest.raises(trusted_workflow_run_validator.ProvenanceValidationError):
        trusted_workflow_run_validator._promotion_proof(
            _promotion_proof_zip(proof, extra_member=extra_member), **kwargs
        )


def test_shared_release_bootstrap_is_approved_bounded_and_has_no_remote_landing_zone():
    workflow_path = REPOSITORY_ROOT / ".github/workflows/bootstrap-shared-release.yml"
    workflow = _load_workflow(workflow_path)
    assert workflow["permissions"] == {"contents": "read"}
    dispatch = workflow["on"]["workflow_dispatch"]
    assert dispatch["inputs"]["confirmation"]["required"] is True
    job = workflow["jobs"]["install"]
    assert job["environment"] == {"name": "production"}
    validation = job["steps"][0]
    assert validation["name"] == "Validate approved main invocation"
    assert "refs/heads/main" in validation["run"]
    assert "BOOTSTRAP_SHARED_RELEASE_V1" in validation["run"]
    checkout = job["steps"][1]
    assert checkout["with"] == {
        "ref": "refs/heads/main",
        "persist-credentials": False,
        "fetch-depth": 1,
    }
    install = next(
        step for step in job["steps"] if step.get("name") == "Install the canonical shared release helpers"
    )
    run = install["run"]
    assert "bootstrap-shared-release-v1.sh" in run
    assert "--bundle-stdin --create-group --add-sudo-user" in run
    assert "with-shared-release-lock.sh" in run
    assert "internal/shared-release-lock-core.sh" in run
    assert "trusted-remote-deploy.sh" in run
    assert ' -p "$VPS_PORT"' in run
    assert "validate-known-hosts.sh" in run
    assert "StrictHostKeyChecking=yes" in run
    assert "ssh-keyscan" not in run
    assert "scp " not in run
    assert "/srv/brianstorm/" not in run
    assert "/var/lib/reno-shared-vps/release.lock" not in run
    assert "mktemp" not in run.split('remote_preflight="', 1)[1].split('"\n', 1)[0]


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
        "image_tag": f"sha-{TRUSTED_TARGET_SHA}",
        "canonical_image_tag": f"sha-{TRUSTED_TARGET_SHA}",
        "control_plane_sha": TRUSTED_TARGET_SHA,
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
    api.promotion_artifact = {
        "id": 8501,
        "name": "trusted-production-promotion-proof",
        "expired": False,
        "workflow_run": {
            "id": TRUSTED_REQUEST_RUN_ID,
            "repository_id": TRUSTED_REPOSITORY_ID,
            "head_repository_id": TRUSTED_REPOSITORY_ID,
            "head_branch": "main",
            "head_sha": TRUSTED_REQUEST_HEAD_SHA,
        },
    }
    if workflow_name == "deploy-prod":
        api.artifacts_for_request = [copy.deepcopy(api.artifact), copy.deepcopy(api.promotion_artifact)]
    else:
        api.artifacts_for_request = [copy.deepcopy(api.artifact)]
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
    promotion_proof = None
    promotion_api = None
    if workflow_name == "deploy-prod":
        promotion_proof, promotion_api, _ = _promotion_validation_fixture()

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
        if artifact_id == api.promotion_artifact["id"]:
            assert promotion_proof is not None
            return _promotion_proof_zip(promotion_proof)
        if artifact_id in {8702, 8703, 8704}:
            assert promotion_api is not None
            return promotion_api.artifact_zip(repository_name, artifact_id)
        assert artifact_id == api.publication_artifact["id"]
        return _trusted_request_zip(
            _trusted_image_publication(), member_name="trusted-image-publication.json"
        )

    api.artifact_zip = artifact_zip
    def workflow_run_artifacts(repository_name, run_id):
        assert repository_name == TRUSTED_REPOSITORY
        if run_id == TRUSTED_REQUEST_RUN_ID:
            return {"artifacts": copy.deepcopy(api.artifacts_for_request)}
        if run_id == TRUSTED_CI_RUN_ID:
            return {"artifacts": [copy.deepcopy(api.publication_artifact)]}
        if run_id in {8302, 8303, 8304}:
            assert promotion_api is not None
            return promotion_api.workflow_run_artifacts(repository_name, run_id)
        raise AssertionError(run_id)
    api.workflow_run_artifacts = workflow_run_artifacts

    if workflow_name == "deploy-prod":
        assert promotion_api is not None
        original_workflow_run = api.workflow_run
        original_workflow_runs = api.workflow_runs
        original_workflow_run_jobs = api.workflow_run_jobs
        control_plane_sha = "c" * 40
        control_plane_run_id = TRUSTED_CI_RUN_ID + 1

        def workflow_run(repository_name, run_id):
            if run_id in {8302, 8303, 8304}:
                return promotion_api.workflow_run(repository_name, run_id)
            return original_workflow_run(repository_name, run_id)

        def workflow_runs(repository_name, workflow_id, head_sha):
            if head_sha == control_plane_sha:
                control_plane_run = copy.deepcopy(api.ci_run)
                control_plane_run.update({"id": control_plane_run_id, "head_sha": control_plane_sha})
                return {"workflow_runs": [control_plane_run]}
            return original_workflow_runs(repository_name, workflow_id, head_sha)

        def workflow_run_jobs(repository_name, run_id):
            if run_id == control_plane_run_id:
                control_plane_job = copy.deepcopy(api.jobs[0])
                control_plane_job.update(
                    {"run_id": control_plane_run_id, "head_sha": control_plane_sha}
                )
                return {"jobs": [control_plane_job]}
            return original_workflow_run_jobs(repository_name, run_id)

        api.main_tip = lambda repository_name: control_plane_sha
        api.workflow_run = workflow_run
        api.workflow_runs = workflow_runs
        api.workflow_run_jobs = workflow_run_jobs
        api.repository_content = promotion_api.repository_content
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
        ("archive-digest", "ci publication artifact digest is invalid"),
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
    elif mutation == "archive-digest":
        api.publication_artifact["digest"] = "sha256:1234"
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


def test_postgres_performance_producer_is_an_isolated_canonical_main_job():
    workflow = _load_workflow(CI_WORKFLOW)
    checks = workflow["jobs"]["checks"]
    producer = workflow["jobs"]["canonical_postgres_performance_baseline_producer"]
    check_steps = checks["steps"]
    producer_steps = producer["steps"]
    baseline = next(
        step
        for step in producer_steps
        if step.get("name") == "Upload canonical-main PostgreSQL performance baseline"
    )
    candidate = next(
        step for step in check_steps if step.get("name") == "Upload PR PostgreSQL performance candidate"
    )

    assert producer["name"] == "canonical PostgreSQL performance baseline producer"
    assert producer["runs-on"] == "ubuntu-latest"
    assert producer["if"] == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main' && "
        "github.repository == 'blankhoney/reno_rss'"
    )
    assert "needs" not in producer
    assert "postgres" in producer["services"]
    assert any(step.get("name") == "Prepare PostgreSQL schema for baseline" for step in producer_steps)
    assert any(step.get("name") == "Seed PostgreSQL performance fixture" for step in producer_steps)
    assert baseline["uses"] == "actions/upload-artifact@v4"
    assert baseline["with"] == {
        "name": "db-postgres-performance-baseline-main",
        "path": "output/performance/db-postgres-ci.json",
        "if-no-files-found": "error",
        "retention-days": 90,
    }
    assert candidate["with"]["name"] == "db-postgres-performance-candidate"
    assert candidate["with"]["retention-days"] == 14
    assert candidate["if"] == "${{ github.event_name == 'pull_request' && !cancelled() }}"
    assert not any(
        step.get("name") == "Upload canonical-main PostgreSQL performance baseline"
        for step in check_steps
    )


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
    assert resolver_step["if"] == "${{ github.event_name == 'pull_request' }}"
    assert compare["if"] == (
        "${{ github.event_name == 'pull_request' && "
        "steps.performance_baseline.outputs.mode == 'comparison' }}"
    )
    assert "--max-regression 3" in compare["run"]


def test_postgres_performance_producer_receives_attempt_scoped_identity():
    workflow = _load_workflow(CI_WORKFLOW)
    producer_step = next(
        step
        for step in workflow["jobs"]["canonical_postgres_performance_baseline_producer"]["steps"]
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

    assert comparison["if"] == (
        "${{ github.event_name == 'pull_request' && "
        "steps.performance_baseline.outputs.mode == 'comparison' && !cancelled() }}"
    )
    assert comparison["with"]["retention-days"] == 90
    assert "db-postgres-comparison.json" in comparison["with"]["path"]
    assert "provenance.json" in comparison["with"]["path"]
    assert bootstrap["if"] == (
        "${{ github.event_name == 'pull_request' && "
        "steps.performance_baseline.outputs.mode == 'bootstrap' && !cancelled() }}"
    )
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

#!/usr/bin/env python3
"""Validate trusted request workflow provenance without executing request data."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, NoReturn, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


SCHEMA_VERSION = "trusted-workflow-ids/v1"
DEFAULT_BRANCH = "main"
MAIN_REF = "refs/heads/main"
REQUEST_WORKFLOW_NAMES = ("deploy-staging", "deploy-prod", "rollback")
REQUEST_WORKFLOW_PATHS = {
    "deploy-staging": ".github/workflows/deploy-staging.yml",
    "deploy-prod": ".github/workflows/deploy-prod.yml",
    "rollback": ".github/workflows/rollback.yml",
}
CI_JOB_NAME = "build / push GHCR images"
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_REPOSITORY_PATTERN = re.compile(r"[^/\s]+/[^/\s]+")


class ProvenanceValidationError(ValueError):
    """A trusted workflow run failed the provenance contract."""


def _reject(reason: str) -> NoReturn:
    raise ProvenanceValidationError(reason)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _reject(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _required_text(value: Mapping[str, Any], key: str, label: str) -> str:
    raw = value.get(key)
    if type(raw) is not str or not raw:
        _reject(f"{label}.{key} must be a non-empty string")
    return cast(str, raw)


def _required_int(value: Mapping[str, Any], key: str, label: str) -> int:
    raw = value.get(key)
    if type(raw) is not int or raw <= 0:
        _reject(f"{label}.{key} must be a positive integer")
    return cast(int, raw)


def _optional_int(value: Mapping[str, Any], key: str, label: str) -> int | None:
    raw = value.get(key)
    if raw is None:
        return None
    if type(raw) is not int or raw <= 0:
        _reject(f"{label}.{key} must be a positive integer or null")
    return cast(int, raw)


def _identity(value: Mapping[str, Any], label: str) -> tuple[int, str]:
    return _required_int(value, "id", label), _required_text(value, "full_name", label)


def _assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        _reject(f"{label} mismatch")


def _assert_repository(
    value: Mapping[str, Any],
    *,
    expected_id: int,
    expected_full_name: str,
    label: str,
) -> None:
    actual_id, actual_full_name = _identity(value, label)
    _assert_equal(actual_id, expected_id, f"{label}.id")
    _assert_equal(actual_full_name, expected_full_name, f"{label}.full_name")


def _assert_sha(value: Mapping[str, Any], key: str, label: str) -> str:
    sha = _required_text(value, key, label)
    if _SHA_PATTERN.fullmatch(sha) is None:
        _reject(f"{label}.{key} must be a 40-character lowercase SHA")
    return sha


def _response_items(response: Mapping[str, Any], key: str, label: str) -> list[Mapping[str, Any]]:
    raw_items = response.get(key)
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes, bytearray)):
        _reject(f"{label}.{key} must be an array")
    items: list[Mapping[str, Any]] = []
    sequence = cast(Sequence[object], raw_items)
    for index, item in enumerate(sequence):
        items.append(_mapping(item, f"{label}.{key}[{index}]"))
    return items


def load_allowlist(path: str | Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _reject(f"unable to read trusted workflow ID allowlist: {error}")
    allowlist = _mapping(payload, "allowlist")
    _assert_equal(allowlist.get("schema_version"), SCHEMA_VERSION, "allowlist.schema_version")
    _assert_equal(allowlist.get("default_branch"), DEFAULT_BRANCH, "allowlist.default_branch")

    request_workflows = _mapping(allowlist.get("request_workflows"), "allowlist.request_workflows")
    if set(request_workflows) != set(REQUEST_WORKFLOW_NAMES):
        _reject("allowlist.request_workflows keys do not match the request workflow allowlist")
    for workflow_name in REQUEST_WORKFLOW_NAMES:
        config = _mapping(
            request_workflows[workflow_name],
            f"allowlist.request_workflows.{workflow_name}",
        )
        label = f"allowlist.request_workflows.{workflow_name}"
        _assert_equal(config.get("path"), REQUEST_WORKFLOW_PATHS[workflow_name], f"{label}.path")
        _assert_equal(config.get("name"), workflow_name, f"{label}.name")
        _optional_int(config, "id", label)
        _required_text(config, "artifact", label)
        expected_request_type = "rollback" if workflow_name == "rollback" else "deploy"
        _assert_equal(config.get("request_type"), expected_request_type, f"{label}.request_type")
        expected_environment = (
            "from-request-after-validation"
            if workflow_name == "rollback"
            else "staging"
            if workflow_name == "deploy-staging"
            else "prod"
        )
        _assert_equal(config.get("environment"), expected_environment, f"{label}.environment")

    ci_workflow = _mapping(allowlist.get("ci_workflow"), "allowlist.ci_workflow")
    _assert_equal(
        ci_workflow.get("path"), ".github/workflows/ci.yml", "allowlist.ci_workflow.path"
    )
    _assert_equal(ci_workflow.get("name"), "ci", "allowlist.ci_workflow.name")
    _optional_int(ci_workflow, "id", "allowlist.ci_workflow")
    return allowlist


def _registered_workflow_id(config: Mapping[str, Any], label: str) -> int:
    workflow_id = _optional_int(config, "id", label)
    if workflow_id is None:
        _reject(f"{label}.id is not registered; refusing name/path-only provenance")
    return workflow_id


def _workflow_identity(
    workflow: Mapping[str, Any],
    *,
    expected_id: int,
    expected_path: str,
    expected_name: str,
    label: str,
    id_key: str = "id",
) -> None:
    _assert_equal(
        _required_int(workflow, id_key, label),
        expected_id,
        f"{label}.{id_key}",
    )
    _assert_equal(_required_text(workflow, "path", label), expected_path, f"{label}.path")
    _assert_equal(_required_text(workflow, "name", label), expected_name, f"{label}.name")


class _StripAuthorizationRedirectHandler(HTTPRedirectHandler):
    """Never forward GitHub API credentials to an artifact storage redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.headers.pop("Authorization", None)
            redirected.headers.pop("X-GitHub-Api-Version", None)
        return redirected


_SAFE_OPENER = build_opener(_StripAuthorizationRedirectHandler())


class GitHubApi:
    """Small read-only GitHub REST client used by the trusted workflow."""

    def __init__(self, token: str, *, base_url: str = "https://api.github.com") -> None:
        if not token:
            _reject("GITHUB_TOKEN is required for provenance lookup")
        self._token = token
        self._base_url = base_url.rstrip("/")

    def _request(self, path: str, *, accept: str = "application/vnd.github+json") -> bytes:
        request = Request(
            f"{self._base_url}{path}",
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with _SAFE_OPENER.open(request, timeout=30) as response:
                return response.read()
        except (HTTPError, URLError, OSError) as error:
            _reject(f"GitHub API request failed: {error}")

    def _json(self, path: str) -> Mapping[str, Any]:
        try:
            payload = json.loads(self._request(path).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            _reject(f"GitHub API returned invalid JSON: {error}")
        return _mapping(payload, "GitHub API response")

    def repository(self, repository: str) -> Mapping[str, Any]:
        return self._json(f"/repos/{quote(repository, safe='/')}")

    def workflow_by_path(self, repository: str, path: str) -> Mapping[str, Any]:
        # GitHub's REST endpoint accepts the workflow file name.  The response
        # is still checked against the full canonical repository-relative path.
        workflow_file = path.rsplit("/", 1)[-1]
        return self._json(
            f"/repos/{quote(repository, safe='/')}/actions/workflows/{quote(workflow_file, safe='')}"
        )

    def workflow_by_id(self, repository: str, workflow_id: int) -> Mapping[str, Any]:
        return self._json(
            f"/repos/{quote(repository, safe='/')}/actions/workflows/{workflow_id}"
        )

    def workflow_run(self, repository: str, run_id: int) -> Mapping[str, Any]:
        return self._json(
            f"/repos/{quote(repository, safe='/')}/actions/runs/{run_id}"
        )

    def workflow_run_artifacts(
        self, repository: str, run_id: int
    ) -> Mapping[str, Any]:
        return self._json(
            f"/repos/{quote(repository, safe='/')}/actions/runs/{run_id}/artifacts"
        )

    def artifact_zip(self, repository: str, artifact_id: int) -> bytes:
        return self._request(
            f"/repos/{quote(repository, safe='/')}/actions/artifacts/{artifact_id}/zip",
            accept="application/vnd.github+json",
        )

    def workflow_runs(
        self, repository: str, workflow_id: int, head_sha: str
    ) -> Mapping[str, Any]:
        query = urlencode({"head_sha": head_sha, "per_page": "100"})
        return self._json(
            f"/repos/{quote(repository, safe='/')}/actions/workflows/{workflow_id}/runs?{query}"
        )

    def workflow_run_jobs(self, repository: str, run_id: int) -> Mapping[str, Any]:
        return self._json(
            f"/repos/{quote(repository, safe='/')}/actions/runs/{run_id}/jobs?per_page=100"
        )


def _assert_event_run_identity(
    event_run: Mapping[str, Any], run: Mapping[str, Any]
) -> None:
    for key in (
        "id",
        "workflow_id",
        "name",
        "event",
        "status",
        "conclusion",
        "head_branch",
        "head_sha",
    ):
        _assert_equal(event_run.get(key), run.get(key), f"workflow_run.{key}")
    # Some workflow_run webhook payloads omit path; the REST run and fixed
    # workflow path/name/ID allowlist remain authoritative in that case.
    if event_run.get("path") is not None:
        _assert_equal(event_run.get("path"), run.get("path"), "workflow_run.path")
    if event_run.get("ref") is not None:
        _assert_equal(event_run.get("ref"), MAIN_REF, "workflow_run.ref")
    if run.get("ref") is not None:
        _assert_equal(run.get("ref"), MAIN_REF, "run.ref")
    if event_run.get("ref") is not None and run.get("ref") is not None:
        _assert_equal(event_run.get("ref"), run.get("ref"), "workflow_run.ref")

    event_repository = _mapping(event_run.get("repository"), "event.workflow_run.repository")
    run_repository = _mapping(run.get("repository"), "run.repository")
    _assert_equal(event_repository.get("id"), run_repository.get("id"), "run.repository.id")
    _assert_equal(
        event_repository.get("full_name"),
        run_repository.get("full_name"),
        "run.repository.full_name",
    )
    event_head_repository = _mapping(
        event_run.get("head_repository"), "event.workflow_run.head_repository"
    )
    run_head_repository = _mapping(run.get("head_repository"), "run.head_repository")
    _assert_equal(
        event_head_repository.get("id"),
        run_head_repository.get("id"),
        "run.head_repository.id",
    )
    _assert_equal(
        event_head_repository.get("full_name"),
        run_head_repository.get("full_name"),
        "run.head_repository.full_name",
    )


def _assert_run_common(
    run: Mapping[str, Any], *, repository_id: int, repository: str, label: str
) -> None:
    _assert_repository(
        _mapping(run.get("repository"), f"{label}.repository"),
        expected_id=repository_id,
        expected_full_name=repository,
        label=f"{label}.repository",
    )
    _assert_repository(
        _mapping(run.get("head_repository"), f"{label}.head_repository"),
        expected_id=repository_id,
        expected_full_name=repository,
        label=f"{label}.head_repository",
    )
    _assert_equal(run.get("head_branch"), DEFAULT_BRANCH, f"{label}.head_branch")
    if "ref" in run:
        _assert_equal(run.get("ref"), MAIN_REF, f"{label}.ref")
    _assert_sha(run, "head_sha", label)


def validate_provenance(
    *,
    event: Mapping[str, Any],
    allowlist: Mapping[str, Any],
    expected_repository: str,
    expected_repository_id: int,
    orchestrator_ref: str,
    api: Any,
) -> dict[str, Any]:
    """Validate one completed request run and its published target SHA."""
    if _REPOSITORY_PATTERN.fullmatch(expected_repository) is None:
        _reject("expected repository must use owner/name form")
    if type(expected_repository_id) is not int or expected_repository_id <= 0:
        _reject("expected repository ID must be a positive integer")
    _assert_equal(orchestrator_ref, MAIN_REF, "orchestrator ref")

    event_run = _mapping(event.get("workflow_run"), "event.workflow_run")
    run_id = _required_int(event_run, "id", "event.workflow_run")
    repository = api.repository(expected_repository)
    _assert_repository(
        repository,
        expected_id=expected_repository_id,
        expected_full_name=expected_repository,
        label="repository",
    )
    _assert_equal(repository.get("default_branch"), DEFAULT_BRANCH, "repository.default_branch")
    _assert_equal(
        allowlist.get("default_branch"), DEFAULT_BRANCH, "allowlist.default_branch"
    )

    run = api.workflow_run(expected_repository, run_id)
    _assert_equal(_required_int(run, "id", "run"), run_id, "run.id")
    _assert_event_run_identity(event_run, run)
    _assert_equal(run.get("status"), "completed", "run.status")
    _assert_equal(run.get("conclusion"), "success", "run.conclusion")
    _assert_equal(run.get("event"), "workflow_dispatch", "run.event")
    _assert_run_common(
        run, repository_id=expected_repository_id, repository=expected_repository, label="run"
    )

    request_workflows = _mapping(allowlist["request_workflows"], "allowlist.request_workflows")
    run_path = _required_text(run, "path", "run")
    matching_configs = [
        config
        for config in request_workflows.values()
        if isinstance(config, Mapping) and config.get("path") == run_path
    ]
    if len(matching_configs) != 1:
        _reject("run.path is not a unique trusted request workflow")
    request_config = matching_configs[0]
    workflow_name = _required_text(request_config, "name", "request workflow")
    workflow_id = _registered_workflow_id(request_config, "request workflow")
    expected_path = _required_text(request_config, "path", "request workflow")
    _workflow_identity(
        run,
        expected_id=workflow_id,
        expected_path=expected_path,
        expected_name=workflow_name,
        label="run",
        id_key="workflow_id",
    )
    _workflow_identity(
        api.workflow_by_path(expected_repository, expected_path),
        expected_id=workflow_id,
        expected_path=expected_path,
        expected_name=workflow_name,
        label="request workflow by path",
    )
    _workflow_identity(
        api.workflow_by_id(expected_repository, workflow_id),
        expected_id=workflow_id,
        expected_path=expected_path,
        expected_name=workflow_name,
        label="request workflow by ID",
    )

    artifact_response = api.workflow_run_artifacts(expected_repository, run_id)
    artifacts = _response_items(artifact_response, "artifacts", "workflow run artifacts")
    expected_artifact_name = _required_text(request_config, "artifact", "request workflow")
    if len(artifacts) != 1 or _required_text(artifacts[0], "name", "artifact") != expected_artifact_name:
        _reject("workflow run artifacts do not match the fixed request artifact")
    artifact = artifacts[0]
    artifact_id = _required_int(artifact, "id", "artifact")
    if artifact.get("expired") is not False:
        _reject("request artifact must not be expired")
    artifact_run = _mapping(artifact.get("workflow_run"), "artifact.workflow_run")
    _assert_equal(artifact_run.get("id"), run_id, "artifact.workflow_run.id")
    _assert_equal(
        artifact_run.get("repository_id"), expected_repository_id, "artifact.workflow_run.repository_id"
    )
    _assert_equal(
        artifact_run.get("head_repository_id"),
        expected_repository_id,
        "artifact.workflow_run.head_repository_id",
    )
    _assert_equal(artifact_run.get("head_branch"), run.get("head_branch"), "artifact head branch")
    _assert_equal(artifact_run.get("head_sha"), run.get("head_sha"), "artifact head SHA")

    validator = _load_request_validator()
    try:
        request = validator.validate_request_zip_bytes(api.artifact_zip(expected_repository, artifact_id))
    except validator.RequestValidationError as error:
        _reject(f"request artifact failed schema validation: {error}")
    expected_request_type = _required_text(request_config, "request_type", "request workflow")
    expected_environment = _required_text(request_config, "environment", "request workflow")
    _assert_equal(request["request_type"], expected_request_type, "request_type")
    if expected_environment == "from-request-after-validation":
        if request["environment"] not in {"staging", "prod"}:
            _reject("rollback request environment must be staging or prod")
    else:
        _assert_equal(request["environment"], expected_environment, "environment")

    ci_config = _mapping(allowlist.get("ci_workflow"), "allowlist.ci_workflow")
    ci_id = _registered_workflow_id(ci_config, "allowlist.ci_workflow")
    ci_path = _required_text(ci_config, "path", "allowlist.ci_workflow")
    ci_name = _required_text(ci_config, "name", "allowlist.ci_workflow")
    _workflow_identity(
        api.workflow_by_path(expected_repository, ci_path),
        expected_id=ci_id,
        expected_path=ci_path,
        expected_name=ci_name,
        label="ci workflow by path",
    )
    _workflow_identity(
        api.workflow_by_id(expected_repository, ci_id),
        expected_id=ci_id,
        expected_path=ci_path,
        expected_name=ci_name,
        label="ci workflow by ID",
    )

    ci_runs = _response_items(
        api.workflow_runs(expected_repository, ci_id, request["deploy_sha"]),
        "workflow_runs",
        "ci workflow runs",
    )
    matching_ci_runs: list[Mapping[str, Any]] = []
    for ci_run in ci_runs:
        if (
            ci_run.get("workflow_id") == ci_id
            and ci_run.get("path") == ci_path
            and ci_run.get("name") == ci_name
            and ci_run.get("event") == "push"
            and ci_run.get("status") == "completed"
            and ci_run.get("conclusion") == "success"
            and ci_run.get("head_sha") == request["deploy_sha"]
            and ci_run.get("head_branch") == DEFAULT_BRANCH
        ):
            if "ref" in ci_run and ci_run.get("ref") != MAIN_REF:
                continue
            try:
                _assert_run_common(
                    ci_run,
                    repository_id=expected_repository_id,
                    repository=expected_repository,
                    label="ci run",
                )
            except ProvenanceValidationError:
                continue
            matching_ci_runs.append(ci_run)
    if not matching_ci_runs:
        _reject("no successful canonical main ci publication run matches deploy_sha")
    if len(matching_ci_runs) != 1:
        _reject("canonical ci publication run is ambiguous")

    publication_run = matching_ci_runs[0]
    publication_run_id = _required_int(publication_run, "id", "ci run")
    publication_run_attempt = _required_int(publication_run, "run_attempt", "ci run")
    jobs = _response_items(
        api.workflow_run_jobs(expected_repository, publication_run_id),
        "jobs",
        "ci run jobs",
    )
    image_jobs = [job for job in jobs if job.get("name") == CI_JOB_NAME]
    if len(image_jobs) != 1:
        _reject("ci publication run must contain exactly one GHCR publication job")
    image_job = image_jobs[0]
    job_run_id = image_job.get("run_id", image_job.get("workflow_run_id"))
    if job_run_id is None:
        _reject("ci image job run identity is missing")
    _assert_equal(job_run_id, publication_run_id, "ci image job workflow run ID")
    _assert_equal(image_job.get("workflow_name"), ci_name, "ci image job workflow name")
    _assert_equal(image_job.get("head_sha"), request["deploy_sha"], "ci image job head SHA")
    _assert_equal(image_job.get("head_branch"), DEFAULT_BRANCH, "ci image job head branch")
    _assert_equal(image_job.get("status"), "completed", "ci image job status")
    _assert_equal(image_job.get("conclusion"), "success", "ci image job conclusion")
    if "workflow_id" in image_job:
        _assert_equal(image_job.get("workflow_id"), ci_id, "ci image job workflow ID")
    if "path" in image_job:
        _assert_equal(image_job.get("path"), ci_path, "ci image job workflow path")

    publication_artifact_response = api.workflow_run_artifacts(
        expected_repository, publication_run_id
    )
    publication_artifacts = _response_items(
        publication_artifact_response, "artifacts", "ci publication artifacts"
    )
    expected_publication_artifact_name = (
        f"trusted-image-publication-{publication_run_id}"
        f"-attempt-{publication_run_attempt}"
    )
    matching_publication_artifacts = [
        artifact
        for artifact in publication_artifacts
        if artifact.get("name") == expected_publication_artifact_name
    ]
    if len(matching_publication_artifacts) != 1:
        _reject("ci publication artifacts do not contain exactly one expected publication artifact")
    publication_artifact = matching_publication_artifacts[0]
    publication_artifact_id = _required_int(publication_artifact, "id", "publication artifact")
    if publication_artifact.get("expired") is not False:
        _reject("ci publication artifact must not be expired")
    publication_artifact_run = _mapping(
        publication_artifact.get("workflow_run"), "publication artifact.workflow_run"
    )
    _assert_equal(
        publication_artifact_run.get("id"),
        publication_run_id,
        "publication artifact.workflow_run.id",
    )
    _assert_equal(
        publication_artifact_run.get("repository_id"),
        expected_repository_id,
        "publication artifact.workflow_run.repository_id",
    )
    _assert_equal(
        publication_artifact_run.get("head_repository_id"),
        expected_repository_id,
        "publication artifact.workflow_run.head_repository_id",
    )
    _assert_equal(
        publication_artifact_run.get("head_branch"),
        DEFAULT_BRANCH,
        "publication artifact head branch",
    )
    _assert_equal(
        publication_artifact_run.get("head_sha"),
        request["deploy_sha"],
        "publication artifact head SHA",
    )

    publication_validator = _load_image_publication_validator()
    try:
        publication = publication_validator.validate_publication_zip_bytes(
            api.artifact_zip(expected_repository, publication_artifact_id),
            expected_repository=expected_repository,
        )
    except publication_validator.PublicationValidationError as error:
        _reject(f"ci publication artifact failed schema validation: {error}")
    _assert_equal(publication["workflow_id"], str(ci_id), "publication.workflow_id")
    _assert_equal(publication["run_id"], str(publication_run_id), "publication.run_id")
    _assert_equal(
        publication["run_attempt"],
        str(publication_run_attempt),
        "publication.run_attempt",
    )
    _assert_equal(publication["deploy_sha"], request["deploy_sha"], "publication.deploy_sha")
    _assert_equal(
        publication["image_tag"],
        f"sha-{request['deploy_sha']}",
        "publication.image_tag",
    )
    _assert_equal(
        request["image_tag"],
        publication["image_tag"],
        "request.image_tag",
    )

    result: dict[str, Any] = {
        "verified": True,
        "request_type": request["request_type"],
        "environment": request["environment"],
        "image_tag": request["image_tag"],
        "deploy_sha": request["deploy_sha"],
        "request_run_id": run_id,
        "artifact_id": artifact_id,
        "ci_run_id": publication_run_id,
        "ci_run_attempt": publication_run_attempt,
        "publication_artifact_id": publication_artifact_id,
        "canonical_image_tag": publication["image_tag"],
    }
    for image_name in ("web", "api", "worker"):
        image = publication["images"][image_name]
        result[f"{image_name}_image_repository"] = image["repository"]
        result[f"{image_name}_image_digest"] = image["digest"]
    return result


def _load_request_validator() -> Any:
    validator_path = Path(__file__).with_name("validate-trusted-deploy-request.py")
    spec = importlib.util.spec_from_file_location("trusted_request_validator", validator_path)
    if spec is None or spec.loader is None:
        _reject("unable to load trusted request validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_image_publication_validator() -> Any:
    validator_path = Path(__file__).with_name("validate-trusted-image-publication.py")
    spec = importlib.util.spec_from_file_location("trusted_image_publication_validator", validator_path)
    if spec is None or spec.loader is None:
        _reject("unable to load trusted image publication validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_outputs(path: str | Path, result: Mapping[str, Any]) -> None:
    lines = []
    for key in (
        "verified",
        "request_type",
        "environment",
        "image_tag",
        "deploy_sha",
        "request_run_id",
        "artifact_id",
        "ci_run_id",
        "ci_run_attempt",
        "publication_artifact_id",
        "canonical_image_tag",
        "web_image_repository",
        "web_image_digest",
        "api_image_repository",
        "api_image_digest",
        "worker_image_repository",
        "worker_image_digest",
    ):
        value = result[key]
        lines.append(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate trusted workflow-run provenance")
    parser.add_argument("--event", type=Path, required=True, help="GitHub event JSON path")
    parser.add_argument("--allowlist", type=Path, required=True, help="workflow ID allowlist path")
    parser.add_argument("--output", type=Path, help="optional GitHub output file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        event = _mapping(json.loads(args.event.read_text(encoding="utf-8")), "event")
        allowlist = load_allowlist(args.allowlist)
        expected_repository = os.environ.get("GITHUB_REPOSITORY", "")
        expected_repository_id_raw = os.environ.get("GITHUB_REPOSITORY_ID", "")
        if not expected_repository_id_raw.isdigit():
            _reject("GITHUB_REPOSITORY_ID must be a positive integer")
        expected_repository_id = int(expected_repository_id_raw)
        orchestrator_ref = os.environ.get("GITHUB_REF", "")
        result = validate_provenance(
            event=event,
            allowlist=allowlist,
            expected_repository=expected_repository,
            expected_repository_id=expected_repository_id,
            orchestrator_ref=orchestrator_ref,
            api=GitHubApi(
                os.environ.get("GITHUB_TOKEN", ""),
                base_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            ),
        )
        if args.output:
            _write_outputs(args.output, result)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProvenanceValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

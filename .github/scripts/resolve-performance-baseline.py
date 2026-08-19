#!/usr/bin/env python3
"""Resolve one trusted canonical-main PostgreSQL performance baseline."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, NoReturn, cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile


SCHEMA_VERSION = "performance-baseline-provenance/v1"
TRUST_SCHEMA_VERSION = "trusted-workflow-ids/v1"
DEFAULT_BRANCH = "main"
MAIN_REF = "refs/heads/main"
CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
CI_WORKFLOW_NAME = "ci"
CHECKS_JOB_NAME = "lint / test / compose-validate / trivy"
BASELINE_MEMBER = "db-postgres-ci.json"
EXPECTED_QUERY_LABELS = {
    "latest-articles",
    "article-title-search",
    "ready-job",
    "due-review",
}
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_DIGEST_PATTERN = re.compile(r"sha256:([0-9a-f]{64})")
_REPOSITORY_PATTERN = re.compile(r"[^/\s]+/[^/\s]+")
MAX_PAGES = 20
MAX_REDIRECTS = 4
MAX_DOWNLOAD_ATTEMPTS = 3
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_REPORT_BYTES = 5 * 1024 * 1024
SAFETY_MARGIN = timedelta(hours=1)
TERMINAL_NON_SUCCESS_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "neutral",
    "skipped",
    "stale",
    "startup_failure",
    "timed_out",
}


class BaselineError(ValueError):
    """The baseline boundary could not be proven safely."""


class CandidateRejected(BaselineError):
    """A canonical-main producer is known not to have completed yet."""


class RaceLost(BaselineError):
    """An exact artifact expired or disappeared after enumeration."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler())


def _reject(reason: str) -> NoReturn:
    raise BaselineError(reason)


def _candidate_reject(reason: str) -> NoReturn:
    raise CandidateRejected(reason)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _reject(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _reject(f"{label} must be an array")
    return cast(Sequence[object], value)


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


def _parse_time(raw: object, label: str) -> datetime:
    if type(raw) is not str or not raw:
        _reject(f"{label} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(cast(str, raw).replace("Z", "+00:00"))
    except ValueError:
        _reject(f"{label} must be an RFC3339 timestamp")
    if parsed.tzinfo is None:
        _reject(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _json_no_duplicates(data: bytes, label: str) -> Mapping[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise BaselineError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _reject(f"{label} is not valid UTF-8 JSON: {error}")
    return _mapping(payload, label)


def load_trust(path: str | Path) -> tuple[int, str, str]:
    payload = _json_no_duplicates(Path(path).read_bytes(), "trust config")
    if payload.get("schema_version") != TRUST_SCHEMA_VERSION:
        _reject("trust config schema_version mismatch")
    ci = _mapping(payload.get("ci_workflow"), "trust config.ci_workflow")
    if ci.get("path") != CI_WORKFLOW_PATH or ci.get("name") != CI_WORKFLOW_NAME:
        _reject("trust config ci workflow path/name mismatch")
    workflow_id = ci.get("id")
    if type(workflow_id) is not int or workflow_id <= 0:
        _reject("trust config ci_workflow.id is not registered")
    return cast(int, workflow_id), CI_WORKFLOW_PATH, CI_WORKFLOW_NAME


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reno-rss-performance-baseline-resolver",
    }


class RawResponse:
    def __init__(self, status: int, headers: Mapping[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body


class GitHubApi:
    """Read-only REST client with bounded pagination, retries, and redirects."""

    def __init__(self, token: str, *, base_url: str = "https://api.github.com") -> None:
        if not token:
            _reject("GITHUB_TOKEN is required")
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            _reject("GITHUB_API_URL must be an absolute HTTPS URL")
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._api_host = parsed.netloc.lower()

    def _send(self, url: str, headers: Mapping[str, str]) -> RawResponse:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with _NO_REDIRECT_OPENER.open(request, timeout=30) as response:
                return RawResponse(response.status, dict(response.headers.items()), response.read())
        except HTTPError as error:
            return RawResponse(error.code, dict(error.headers.items()), error.read())
        except (URLError, TimeoutError, OSError) as error:
            raise ConnectionError(str(error)) from error

    def _api_request(self, path_or_url: str) -> RawResponse:
        url = path_or_url if path_or_url.startswith("https://") else f"{self._base_url}{path_or_url}"
        if urlparse(url).netloc.lower() != self._api_host:
            _reject("GitHub API pagination redirected to a different host")
        try:
            response = self._send(url, _github_headers(self._token))
        except ConnectionError as error:
            _reject(f"GitHub API request failed: {error}")
        if response.status != 200:
            _reject(f"GitHub API request failed with HTTP {response.status}")
        return response

    def _json(self, path_or_url: str) -> Mapping[str, Any]:
        return _json_no_duplicates(self._api_request(path_or_url).body, "GitHub API response")

    def repository(self, repository: str) -> Mapping[str, Any]:
        return self._json(f"/repos/{quote(repository, safe='/')}")

    def workflow(self, repository: str, workflow_id: int) -> Mapping[str, Any]:
        return self._json(
            f"/repos/{quote(repository, safe='/')}/actions/workflows/{workflow_id}"
        )

    def workflow_run(self, repository: str, run_id: int) -> Mapping[str, Any]:
        return self._json(f"/repos/{quote(repository, safe='/')}/actions/runs/{run_id}")

    def artifact(self, repository: str, artifact_id: int) -> Mapping[str, Any]:
        url = (
            f"{self._base_url}/repos/{quote(repository, safe='/')}"
            f"/actions/artifacts/{artifact_id}"
        )
        last_error = ""
        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            try:
                response = self._send(url, _github_headers(self._token))
            except ConnectionError as error:
                last_error = str(error)
            else:
                if response.status in {404, 410}:
                    raise RaceLost(f"exact artifact metadata returned HTTP {response.status}")
                if response.status == 403:
                    _reject("exact artifact metadata returned HTTP 403")
                if response.status == 200:
                    return _json_no_duplicates(response.body, "artifact metadata")
                if not 500 <= response.status <= 599:
                    _reject(f"artifact metadata request failed with HTTP {response.status}")
                last_error = f"HTTP {response.status}"
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                _reject(
                    f"artifact {artifact_id} metadata failed after "
                    f"{MAX_DOWNLOAD_ATTEMPTS} same-ID attempts: {last_error}"
                )
        raise AssertionError("unreachable")

    def artifacts(self, repository: str, artifact_name: str) -> list[Mapping[str, Any]]:
        query = urlencode({"name": artifact_name, "per_page": "100"})
        next_url: str | None = (
            f"{self._base_url}/repos/{quote(repository, safe='/')}/actions/artifacts?{query}"
        )
        pages = 0
        expected_total: int | None = None
        by_id: dict[int, Mapping[str, Any]] = {}
        while next_url is not None:
            pages += 1
            if pages > MAX_PAGES:
                _reject("artifact pagination coverage incomplete: page cap reached")
            response = self._api_request(next_url)
            payload = _json_no_duplicates(response.body, "artifact enumeration")
            expected_total = _pagination_total(payload, expected_total, "artifact")
            for index, raw in enumerate(_sequence(payload.get("artifacts"), "artifacts")):
                artifact = _mapping(raw, f"artifacts[{index}]")
                artifact_id = _required_int(artifact, "id", f"artifacts[{index}]")
                if _required_text(artifact, "name", f"artifacts[{index}]") != artifact_name:
                    _reject("artifact enumeration returned a non-matching name")
                if artifact_id in by_id:
                    _reject("artifact pagination coverage incomplete: duplicate artifact ID")
                by_id[artifact_id] = artifact
            next_url = _next_link(response.headers.get("Link"))
        _assert_pagination_complete(expected_total, len(by_id), "artifact")
        return sorted(
            by_id.values(),
            key=lambda artifact: (
                _parse_time(artifact.get("created_at"), "artifact.created_at"),
                _required_int(artifact, "id", "artifact"),
            ),
            reverse=True,
        )

    def jobs(
        self, repository: str, run_id: int, run_attempt: int
    ) -> list[Mapping[str, Any]]:
        next_url: str | None = (
            f"{self._base_url}/repos/{quote(repository, safe='/')}/actions/runs/{run_id}"
            f"/attempts/{run_attempt}/jobs?per_page=100"
        )
        pages = 0
        expected_total: int | None = None
        by_id: dict[int, Mapping[str, Any]] = {}
        while next_url is not None:
            pages += 1
            if pages > MAX_PAGES:
                _reject("attempt job pagination coverage incomplete: page cap reached")
            response = self._api_request(next_url)
            payload = _json_no_duplicates(response.body, "attempt jobs")
            expected_total = _pagination_total(payload, expected_total, "attempt job")
            for index, raw in enumerate(_sequence(payload.get("jobs"), "jobs")):
                job = _mapping(raw, f"jobs[{index}]")
                job_id = _required_int(job, "id", f"jobs[{index}]")
                if job_id in by_id:
                    _reject("attempt job pagination coverage incomplete: duplicate job ID")
                by_id[job_id] = job
            next_url = _next_link(response.headers.get("Link"))
        _assert_pagination_complete(expected_total, len(by_id), "attempt job")
        return list(by_id.values())

    def download(self, repository: str, artifact_id: int) -> bytes:
        url = (
            f"{self._base_url}/repos/{quote(repository, safe='/')}"
            f"/actions/artifacts/{artifact_id}/zip"
        )
        last_error = ""
        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            try:
                return self._download_once(url)
            except RaceLost:
                raise
            except ConnectionError as error:
                last_error = str(error)
            except _RetryableDownload as error:
                last_error = str(error)
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                _reject(
                    f"artifact {artifact_id} download failed after "
                    f"{MAX_DOWNLOAD_ATTEMPTS} same-ID attempts: {last_error}"
                )
        raise AssertionError("unreachable")

    def _download_once(self, initial_url: str) -> bytes:
        url = initial_url
        headers = _github_headers(self._token)
        for redirect_count in range(MAX_REDIRECTS + 1):
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                _reject("artifact download redirect must use HTTPS")
            if parsed.netloc.lower() != self._api_host:
                headers = {}
            try:
                response = self._send(url, headers)
            except ConnectionError:
                raise
            if response.status in {301, 302, 303, 307, 308}:
                if redirect_count == MAX_REDIRECTS:
                    _reject("artifact download exceeded redirect limit")
                location = response.headers.get("Location")
                if not location:
                    _reject("artifact download redirect is missing Location")
                next_url = urljoin(url, location)
                next_parsed = urlparse(next_url)
                if next_parsed.scheme != "https" or not next_parsed.netloc:
                    _reject("artifact download redirect must use HTTPS")
                if next_parsed.netloc.lower() != self._api_host:
                    headers = {}
                else:
                    headers = _github_headers(self._token)
                url = next_url
                continue
            if response.status in {404, 410}:
                raise RaceLost(f"exact artifact download returned HTTP {response.status}")
            if response.status == 403:
                _reject("exact artifact download returned HTTP 403")
            if 500 <= response.status <= 599:
                raise _RetryableDownload(f"HTTP {response.status}")
            if response.status != 200:
                _reject(f"exact artifact download returned HTTP {response.status}")
            if len(response.body) > MAX_ZIP_BYTES:
                _reject("artifact ZIP exceeds size limit")
            return response.body
        raise AssertionError("unreachable")


class _RetryableDownload(Exception):
    pass


def _pagination_total(
    payload: Mapping[str, Any], expected: int | None, label: str
) -> int:
    total = payload.get("total_count")
    if type(total) is not int or total < 0:
        _reject(f"{label} pagination total_count must be a non-negative integer")
    if expected is not None and total != expected:
        _reject(f"{label} pagination total_count changed between pages")
    return cast(int, total)


def _assert_pagination_complete(expected: int | None, collected: int, label: str) -> None:
    if expected is None or collected != expected:
        _reject(
            f"{label} pagination coverage incomplete: "
            f"expected {expected} unique records, collected {collected}"
        )


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for segment in header.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>;\s*rel="([^"]+)"\s*', segment)
        if match and match.group(2) == "next":
            parsed = urlparse(match.group(1))
            query = parse_qs(parsed.query)
            if query.get("per_page") != ["100"]:
                _reject("pagination next link changed per_page")
            return match.group(1)
    return None


def _artifact_snapshot(artifact: Mapping[str, Any]) -> tuple[object, ...]:
    workflow_run = _mapping(artifact.get("workflow_run"), "artifact.workflow_run")
    return (
        artifact.get("id"),
        artifact.get("name"),
        artifact.get("expired"),
        artifact.get("created_at"),
        artifact.get("updated_at"),
        artifact.get("expires_at"),
        artifact.get("digest"),
        workflow_run.get("id"),
        workflow_run.get("repository_id"),
        workflow_run.get("head_repository_id"),
        workflow_run.get("head_branch"),
        workflow_run.get("head_sha"),
    )


def _snapshot(artifacts: Sequence[Mapping[str, Any]]) -> tuple[tuple[object, ...], ...]:
    return tuple(_artifact_snapshot(artifact) for artifact in artifacts)


def _assert_repository(
    value: object, expected_id: int, expected_name: str, label: str
) -> None:
    repository = _mapping(value, label)
    if repository.get("id") != expected_id or repository.get("full_name") != expected_name:
        _reject(f"{label} does not match canonical repository")


def validate_run(
    run: Mapping[str, Any],
    *,
    repository: str,
    repository_id: int,
    workflow_id: int,
) -> tuple[int, int, str]:
    run_id = _required_int(run, "id", "run")
    run_attempt = _required_int(run, "run_attempt", "run")
    head_sha = _required_text(run, "head_sha", "run")
    if _SHA_PATTERN.fullmatch(head_sha) is None:
        _reject("run.head_sha is not a lowercase 40-character SHA")
    expected = {
        "workflow_id": workflow_id,
        "event": "push",
        "head_branch": DEFAULT_BRANCH,
    }
    for key, value in expected.items():
        if run.get(key) != value:
            _reject(f"run.{key} mismatch")
    _assert_repository(run.get("repository"), repository_id, repository, "run.repository")
    _assert_repository(
        run.get("head_repository"), repository_id, repository, "run.head_repository"
    )
    status = run.get("status")
    if status in {"queued", "in_progress", "requested", "waiting", "pending"}:
        _candidate_reject(f"run {run_id} is not completed")
    if status != "completed":
        _reject("run.status mismatch")
    conclusion = run.get("conclusion")
    if conclusion in TERMINAL_NON_SUCCESS_CONCLUSIONS:
        _candidate_reject(f"run {run_id} did not succeed")
    if conclusion != "success":
        _reject("run.conclusion mismatch")
    return run_id, run_attempt, head_sha


def validate_jobs(
    jobs: Sequence[Mapping[str, Any]], *, run_id: int, run_attempt: int, head_sha: str
) -> None:
    matches = [job for job in jobs if job.get("name") == CHECKS_JOB_NAME]
    if len(matches) != 1:
        _reject("attempt must contain exactly one checks display-name job")
    job = matches[0]
    expected = {
        "run_id": run_id,
        "run_attempt": run_attempt,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "success",
    }
    for key, value in expected.items():
        if job.get(key) != value:
            _reject(f"checks job {key} mismatch")


def _validate_artifact_workflow_run(
    artifact_run: Mapping[str, Any], *, repository_id: int, run_id: int, head_sha: str
) -> None:
    expected = {
        "id": run_id,
        "repository_id": repository_id,
        "head_repository_id": repository_id,
        "head_branch": DEFAULT_BRANCH,
        "head_sha": head_sha,
    }
    for key, value in expected.items():
        if artifact_run.get(key) != value:
            _reject(f"artifact.workflow_run.{key} mismatch")


def validate_artifact_metadata(
    artifact: Mapping[str, Any],
    *,
    artifact_name: str,
    repository_id: int,
    run_id: int,
    head_sha: str,
    now: datetime,
) -> tuple[int, str, datetime]:
    artifact_id = _required_int(artifact, "id", "artifact")
    if artifact.get("name") != artifact_name:
        _reject("artifact name mismatch")
    expired = artifact.get("expired")
    if type(expired) is not bool:
        _reject("artifact.expired must be a boolean")
    if expired:
        raise RaceLost(f"artifact {artifact_id} is expired")
    expires_at = _parse_time(artifact.get("expires_at"), "artifact.expires_at")
    if expires_at <= now + SAFETY_MARGIN:
        raise RaceLost(f"artifact {artifact_id} is inside expiry safety margin")
    digest = _required_text(artifact, "digest", "artifact")
    if _DIGEST_PATTERN.fullmatch(digest) is None:
        _reject("artifact.digest must use sha256:<64 lowercase hex>")
    artifact_run = _mapping(artifact.get("workflow_run"), "artifact.workflow_run")
    _validate_artifact_workflow_run(
        artifact_run,
        repository_id=repository_id,
        run_id=run_id,
        head_sha=head_sha,
    )
    return artifact_id, digest, expires_at


def validate_report(
    report_bytes: bytes, *, run_id: int, run_attempt: int, head_sha: str
) -> Mapping[str, Any]:
    report = _json_no_duplicates(report_bytes, "baseline report")
    if report.get("schemaVersion") != 2:
        _reject("baseline report schemaVersion must be 2")
    if report.get("status") != "MEASURED":
        _reject("baseline report status must be MEASURED")
    producer = _mapping(report.get("producer"), "baseline report.producer")
    if set(producer) != {"runId", "runAttempt"}:
        _reject("baseline report producer fields mismatch")
    if producer.get("runId") != run_id or producer.get("runAttempt") != run_attempt:
        _reject("baseline report producer run identity mismatch")
    candidate = _mapping(report.get("candidate"), "baseline report.candidate")
    if candidate.get("localGitRevision") != head_sha:
        _reject("baseline report candidate.localGitRevision mismatch")
    environment = _mapping(report.get("environment"), "baseline report.environment")
    if environment.get("databaseDialect") != "postgresql":
        _reject("baseline report database dialect mismatch")
    iterations = environment.get("iterations")
    warmups = environment.get("warmups")
    if type(iterations) is not int or iterations <= 0:
        _reject("baseline report iterations must be positive")
    if type(warmups) is not int or warmups <= 0:
        _reject("baseline report warmups must be positive")
    queries = _sequence(report.get("queries"), "baseline report.queries")
    labels: set[str] = set()
    for index, raw_query in enumerate(queries):
        query = _mapping(raw_query, f"baseline report.queries[{index}]")
        label = _required_text(query, "label", f"baseline report.queries[{index}]")
        if label in labels:
            _reject("baseline report contains duplicate query labels")
        labels.add(label)
        samples = _sequence(query.get("samples"), f"query {label}.samples")
        if len(samples) != iterations:
            _reject(f"query {label} sample count mismatch")
        for sample_index, raw_sample in enumerate(samples, 1):
            sample = _mapping(raw_sample, f"query {label}.samples[{sample_index - 1}]")
            if sample.get("sampleIndex") != sample_index:
                _reject(f"query {label} sampleIndex mismatch")
            duration = sample.get("durationMs")
            row_count = sample.get("rowCount")
            if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
                _reject(f"query {label} durationMs must be positive")
            if type(row_count) is not int or row_count < 0:
                _reject(f"query {label} rowCount must be a non-negative integer")
        summary = _mapping(query.get("summary"), f"query {label}.summary")
        for metric_name in ("durationMs", "rowCount"):
            metric = _mapping(summary.get(metric_name), f"query {label}.{metric_name}")
            if set(metric) != {"median", "p95", "min", "max"}:
                _reject(f"query {label} {metric_name} summary fields mismatch")
            for value in metric.values():
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                    _reject(f"query {label} {metric_name} summary value is invalid")
    if labels != EXPECTED_QUERY_LABELS:
        _reject("baseline report query labels mismatch")
    return report


def extract_report(zip_bytes: bytes) -> bytes:
    if len(zip_bytes) > MAX_ZIP_BYTES:
        _reject("artifact ZIP exceeds size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            infos = archive.infolist()
            if len(infos) != 1:
                _reject("artifact ZIP must contain exactly one member")
            info = infos[0]
            if info.filename != BASELINE_MEMBER or info.is_dir():
                _reject(f"artifact ZIP member must be {BASELINE_MEMBER}")
            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFREG}:
                _reject("artifact ZIP member must be a regular file")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                _reject("artifact ZIP uses an unsupported compression method")
            if info.file_size > MAX_REPORT_BYTES:
                _reject("baseline report exceeds size limit")
            with archive.open(info) as member:
                data = member.read(MAX_REPORT_BYTES + 1)
            if len(data) > MAX_REPORT_BYTES or len(data) != info.file_size:
                _reject("baseline report size mismatch")
            return data
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError) as error:
        _reject(f"artifact ZIP is invalid: {error}")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _workflow_identity(
    workflow: Mapping[str, Any], workflow_id: int, workflow_path: str, workflow_name: str
) -> None:
    if (
        workflow.get("id") != workflow_id
        or workflow.get("path") != workflow_path
        or workflow.get("name") != workflow_name
    ):
        _reject("canonical workflow ID/path/name mismatch")


def _candidate_expired(artifact: Mapping[str, Any], now: datetime) -> bool:
    expired = artifact.get("expired")
    if type(expired) is not bool:
        _reject("artifact.expired must be a boolean")
    if expired:
        return True
    return _parse_time(artifact.get("expires_at"), "artifact.expires_at") <= now + SAFETY_MARGIN


def _resolve_candidate(
    api: Any,
    artifact: Mapping[str, Any],
    *,
    repository: str,
    repository_id: int,
    workflow_id: int,
    artifact_name: str,
    output: Path,
    provenance_output: Path,
    now: datetime,
) -> Mapping[str, Any]:
    artifact_id = _required_int(artifact, "id", "artifact")
    artifact_run = _mapping(artifact.get("workflow_run"), "artifact.workflow_run")
    run_id = _required_int(artifact_run, "id", "artifact.workflow_run")
    run = api.workflow_run(repository, run_id)
    selected_run_id, run_attempt, head_sha = validate_run(
        run,
        repository=repository,
        repository_id=repository_id,
        workflow_id=workflow_id,
    )
    _validate_artifact_workflow_run(
        artifact_run,
        repository_id=repository_id,
        run_id=selected_run_id,
        head_sha=head_sha,
    )
    validate_jobs(
        api.jobs(repository, selected_run_id, run_attempt),
        run_id=selected_run_id,
        run_attempt=run_attempt,
        head_sha=head_sha,
    )
    exact = api.artifact(repository, artifact_id)
    exact_id, rest_digest, expires_at = validate_artifact_metadata(
        exact,
        artifact_name=artifact_name,
        repository_id=repository_id,
        run_id=selected_run_id,
        head_sha=head_sha,
        now=now,
    )
    if exact_id != artifact_id:
        _reject("exact artifact ID mismatch")
    zip_bytes = api.download(repository, artifact_id)
    computed_digest = f"sha256:{hashlib.sha256(zip_bytes).hexdigest()}"
    if computed_digest != rest_digest:
        _reject("artifact ZIP SHA-256 does not match REST digest")
    report_bytes = extract_report(zip_bytes)
    validate_report(
        report_bytes,
        run_id=selected_run_id,
        run_attempt=run_attempt,
        head_sha=head_sha,
    )
    provenance = {
        "schemaVersion": SCHEMA_VERSION,
        "mode": "comparison",
        "repository": {"id": repository_id, "fullName": repository},
        "workflow": {
            "id": workflow_id,
            "path": CI_WORKFLOW_PATH,
            "name": CI_WORKFLOW_NAME,
        },
        "run": {
            "id": selected_run_id,
            "attempt": run_attempt,
            "headSha": head_sha,
        },
        "artifact": {
            "id": artifact_id,
            "name": artifact_name,
            "restDigest": rest_digest,
            "computedDigest": computed_digest,
            "createdAt": _required_text(exact, "created_at", "artifact"),
            "expiresAt": expires_at.isoformat(),
        },
        "resolvedAt": now.isoformat(),
    }
    _atomic_write(output, report_bytes)
    _atomic_write(
        provenance_output,
        (json.dumps(provenance, ensure_ascii=True, indent=2) + "\n").encode(),
    )
    return provenance


def resolve(
    *,
    api: Any,
    repository: str,
    repository_id: int,
    workflow_id: int,
    workflow_path: str,
    workflow_name: str,
    artifact_name: str,
    output: Path,
    provenance_output: Path,
    event_name: str,
    ref: str,
    now: datetime,
) -> Mapping[str, Any]:
    if _REPOSITORY_PATTERN.fullmatch(repository) is None:
        _reject("repository must use owner/name form")
    if type(repository_id) is not int or repository_id <= 0:
        _reject("repository ID must be a positive integer")
    canonical = api.repository(repository)
    if canonical.get("id") != repository_id or canonical.get("full_name") != repository:
        _reject("canonical repository identity mismatch")
    if canonical.get("default_branch") != DEFAULT_BRANCH:
        _reject("canonical repository default branch mismatch")
    _workflow_identity(api.workflow(repository, workflow_id), workflow_id, workflow_path, workflow_name)

    def try_candidates(
        artifacts: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any] | None:
        for artifact in artifacts:
            if _candidate_expired(artifact, now):
                continue
            try:
                return _resolve_candidate(
                    api,
                    artifact,
                    repository=repository,
                    repository_id=repository_id,
                    workflow_id=workflow_id,
                    artifact_name=artifact_name,
                    output=output,
                    provenance_output=provenance_output,
                    now=now,
                )
            except (CandidateRejected, RaceLost):
                continue
        return None

    first = api.artifacts(repository, artifact_name)
    resolved = try_candidates(first)
    if resolved is not None:
        return resolved

    if event_name != "push" or ref != MAIN_REF:
        _reject("no unexpired trusted canonical-main baseline is available; PR bootstrap is forbidden")

    previous = _snapshot(first)
    current_artifacts = api.artifacts(repository, artifact_name)
    resolved = try_candidates(current_artifacts)
    if resolved is not None:
        return resolved
    current = _snapshot(current_artifacts)
    if current != previous:
        _reject("artifact enumeration is not stable; bootstrap is forbidden")
    provenance = {
        "schemaVersion": SCHEMA_VERSION,
        "mode": "bootstrap",
        "repository": {"id": repository_id, "fullName": repository},
        "workflow": {
            "id": workflow_id,
            "path": workflow_path,
            "name": workflow_name,
        },
        "artifactName": artifact_name,
        "enumeratedArtifactIds": [snapshot[0] for snapshot in previous],
        "resolvedAt": now.isoformat(),
        "message": (
            "BOOTSTRAP: two complete stable enumerations found no trusted baseline; "
            "no regression comparison was possible"
        ),
    }
    _atomic_write(
        provenance_output,
        (json.dumps(provenance, ensure_ascii=True, indent=2) + "\n").encode(),
    )
    return provenance


def freshness(
    *,
    api: Any,
    repository: str,
    repository_id: int,
    workflow_id: int,
    workflow_path: str,
    workflow_name: str,
    artifact_name: str,
    now: datetime,
    threshold: timedelta,
) -> Mapping[str, Any]:
    canonical = api.repository(repository)
    if canonical.get("id") != repository_id or canonical.get("full_name") != repository:
        _reject("canonical repository identity mismatch")
    _workflow_identity(api.workflow(repository, workflow_id), workflow_id, workflow_path, workflow_name)
    for artifact in api.artifacts(repository, artifact_name):
        if _candidate_expired(artifact, now):
            continue
        artifact_run = _mapping(artifact.get("workflow_run"), "artifact.workflow_run")
        run_id = _required_int(artifact_run, "id", "artifact.workflow_run")
        try:
            run = api.workflow_run(repository, run_id)
            selected_run_id, run_attempt, head_sha = validate_run(
                run,
                repository=repository,
                repository_id=repository_id,
                workflow_id=workflow_id,
            )
            _validate_artifact_workflow_run(
                artifact_run,
                repository_id=repository_id,
                run_id=selected_run_id,
                head_sha=head_sha,
            )
            validate_jobs(
                api.jobs(repository, selected_run_id, run_attempt),
                run_id=selected_run_id,
                run_attempt=run_attempt,
                head_sha=head_sha,
            )
            exact = api.artifact(repository, _required_int(artifact, "id", "artifact"))
            artifact_id, digest, expires_at = validate_artifact_metadata(
                exact,
                artifact_name=artifact_name,
                repository_id=repository_id,
                run_id=selected_run_id,
                head_sha=head_sha,
                now=now,
            )
        except (CandidateRejected, RaceLost):
            continue
        remaining = expires_at - now
        result = {
            "mode": "freshness",
            "artifactId": artifact_id,
            "runId": selected_run_id,
            "runAttempt": run_attempt,
            "headSha": head_sha,
            "digest": digest,
            "expiresAt": expires_at.isoformat(),
            "remainingSeconds": int(remaining.total_seconds()),
            "fresh": remaining >= threshold,
        }
        if not result["fresh"]:
            _reject(
                f"trusted baseline expires at {expires_at.isoformat()}, below freshness threshold"
            )
        return result
    _reject("no unexpired trusted canonical-main baseline is available")


def _write_github_output(path: str | Path, result: Mapping[str, Any]) -> None:
    fields: dict[str, object] = {"mode": result["mode"]}
    if result["mode"] == "comparison":
        run = _mapping(result["run"], "result.run")
        artifact = _mapping(result["artifact"], "result.artifact")
        fields.update(
            {
                "run_id": run["id"],
                "run_attempt": run["attempt"],
                "head_sha": run["headSha"],
                "artifact_id": artifact["id"],
                "expires_at": artifact["expiresAt"],
                "digest": artifact["restDigest"],
            }
        )
    Path(path).write_text(
        "".join(f"{key}={value}\n" for key, value in fields.items()), encoding="utf-8"
    )


def _write_freshness_summary(result: Mapping[str, Any] | None, error: str | None = None) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        return
    lines = ["### PostgreSQL performance baseline freshness"]
    if result is not None:
        lines.extend(
            [
                f"- status: `{'fresh' if result['fresh'] else 'stale'}`",
                f"- artifact: `{result['artifactId']}`",
                f"- run: `{result['runId']}` attempt `{result['runAttempt']}`",
                f"- head SHA: `{result['headSha']}`",
                f"- expires_at: `{result['expiresAt']}`",
                f"- digest: `{result['digest']}`",
            ]
        )
    else:
        safe_error = (error or "unknown error").replace("`", "'").replace("\n", " ")
        lines.extend(["- status: `failed`", f"- reason: `{safe_error}`"])
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", type=int, required=True)
    parser.add_argument("--trust-config", type=Path, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--provenance-output", type=Path)
    parser.add_argument("--event-name")
    parser.add_argument("--ref")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--freshness-threshold-days", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    is_freshness = args.freshness_threshold_days is not None
    try:
        workflow_id, workflow_path, workflow_name = load_trust(args.trust_config)
        api = GitHubApi(
            os.environ.get("GITHUB_TOKEN", ""),
            base_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        )
        now = datetime.now(UTC)
        if args.freshness_threshold_days is not None:
            if args.freshness_threshold_days <= 0:
                _reject("freshness threshold must be positive")
            result = freshness(
                api=api,
                repository=args.repository,
                repository_id=args.repository_id,
                workflow_id=workflow_id,
                workflow_path=workflow_path,
                workflow_name=workflow_name,
                artifact_name=args.artifact_name,
                now=now,
                threshold=timedelta(days=args.freshness_threshold_days),
            )
        else:
            if not all(
                [args.output, args.provenance_output, args.event_name, args.ref]
            ):
                _reject("resolve mode requires output, provenance-output, event-name, and ref")
            result = resolve(
                api=api,
                repository=args.repository,
                repository_id=args.repository_id,
                workflow_id=workflow_id,
                workflow_path=workflow_path,
                workflow_name=workflow_name,
                artifact_name=args.artifact_name,
                output=args.output,
                provenance_output=args.provenance_output,
                event_name=args.event_name,
                ref=args.ref,
                now=now,
            )
        if args.github_output:
            _write_github_output(args.github_output, result)
        if is_freshness:
            _write_freshness_summary(result)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0
    except (OSError, BaselineError) as error:
        if is_freshness:
            _write_freshness_summary(None, str(error))
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
from typing import Any
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESOLVER_PATH = REPOSITORY_ROOT / ".github/scripts/resolve-performance-baseline.py"
PRODUCER_PATH = REPOSITORY_ROOT / "apps/worker/scripts/db-performance-baseline.py"
COMPARATOR_PATH = REPOSITORY_ROOT / "infra/scripts/check-performance-baseline.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = _load(RESOLVER_PATH, "resolve_performance_baseline")
producer = _load(PRODUCER_PATH, "db_performance_baseline")
comparator = _load(COMPARATOR_PATH, "check_performance_baseline")

REPOSITORY = "example/project"
REPOSITORY_ID = 1001
WORKFLOW_ID = 2001
RUN_ID = 3001
RUN_ATTEMPT = 2
ARTIFACT_ID = 4001
JOB_ID = 5001
HEAD_SHA = "a" * 40
ARTIFACT_NAME = "db-postgres-performance-baseline-main"
NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def _report(*, run_id=RUN_ID, run_attempt=RUN_ATTEMPT, head_sha=HEAD_SHA) -> dict[str, Any]:
    queries = []
    for label in sorted(resolver.EXPECTED_QUERY_LABELS):
        samples = [
            {"durationMs": 1.0, "rowCount": 1, "sampleIndex": 1},
            {"durationMs": 2.0, "rowCount": 1, "sampleIndex": 2},
        ]
        queries.append(
            {
                "label": label,
                "samples": samples,
                "summary": {
                    "durationMs": {"median": 1.0, "p95": 2.0, "min": 1.0, "max": 2.0},
                    "rowCount": {"median": 1.0, "p95": 1.0, "min": 1.0, "max": 1.0},
                },
            }
        )
    return {
        "schemaVersion": 2,
        "generatedAt": NOW.isoformat(),
        "producer": {"runId": run_id, "runAttempt": run_attempt},
        "candidate": {"localGitRevision": head_sha, "runtime": "read-only PostgreSQL"},
        "environment": {
            "databaseDialect": "postgresql",
            "iterations": 2,
            "platform": "test",
            "python": "3.12",
            "warmups": 1,
        },
        "status": "MEASURED",
        "queries": queries,
    }


def _zip(report: dict[str, Any] | None = None, *, member=resolver.BASELINE_MEMBER) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, json.dumps(report or _report(), separators=(",", ":")))
    return output.getvalue()


def _artifact(artifact_id=ARTIFACT_ID, *, run_id=RUN_ID, expired=False, expires_days=30):
    return {
        "id": artifact_id,
        "name": ARTIFACT_NAME,
        "expired": expired,
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:01:00Z",
        "expires_at": (NOW + timedelta(days=expires_days)).isoformat(),
        "digest": "sha256:" + "0" * 64,
        "workflow_run": {
            "id": run_id,
            "repository_id": REPOSITORY_ID,
            "head_repository_id": REPOSITORY_ID,
            "head_branch": "main",
            "head_sha": HEAD_SHA,
        },
    }


def _run(run_id=RUN_ID):
    return {
        "id": run_id,
        "run_attempt": RUN_ATTEMPT,
        "workflow_id": WORKFLOW_ID,
        "event": "push",
        "head_branch": "main",
        "head_sha": HEAD_SHA,
        "status": "completed",
        "conclusion": "success",
        "repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
        "head_repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
    }


def _job(run_id=RUN_ID, job_id=JOB_ID):
    return {
        "id": job_id,
        "name": resolver.BASELINE_PRODUCER_JOB_NAME,
        "run_id": run_id,
        "run_attempt": RUN_ATTEMPT,
        "head_sha": HEAD_SHA,
        "status": "completed",
        "conclusion": "success",
    }


class FakeApi:
    def __init__(self, artifacts=None):
        self.enumerations = [copy.deepcopy(artifacts or [_artifact()])]
        self.runs = {RUN_ID: _run()}
        self.jobs_by_run = {RUN_ID: [_job()]}
        self.exact = {ARTIFACT_ID: _artifact()}
        self.zips = {ARTIFACT_ID: _zip()}
        self.calls: list[tuple[Any, ...]] = []
        self._refresh_digests()

    def _refresh_digests(self):
        for artifact_id, archive in self.zips.items():
            if artifact_id in self.exact:
                self.exact[artifact_id]["digest"] = f"sha256:{hashlib.sha256(archive).hexdigest()}"
            for enumeration in self.enumerations:
                for artifact in enumeration:
                    if artifact["id"] == artifact_id:
                        artifact["digest"] = f"sha256:{hashlib.sha256(archive).hexdigest()}"

    def repository(self, repository):
        assert repository == REPOSITORY
        return {"id": REPOSITORY_ID, "full_name": REPOSITORY, "default_branch": "main"}

    def workflow(self, repository, workflow_id):
        assert repository == REPOSITORY and workflow_id == WORKFLOW_ID
        return {"id": WORKFLOW_ID, "path": resolver.CI_WORKFLOW_PATH, "name": "ci"}

    def artifacts(self, repository, artifact_name):
        self.calls.append(("artifacts", repository, artifact_name))
        index = min(sum(call[0] == "artifacts" for call in self.calls) - 1, len(self.enumerations) - 1)
        return copy.deepcopy(self.enumerations[index])

    def workflow_run(self, repository, run_id):
        self.calls.append(("run", run_id))
        return copy.deepcopy(self.runs[run_id])

    def jobs(self, repository, run_id, run_attempt):
        self.calls.append(("jobs", run_id, run_attempt))
        return copy.deepcopy(self.jobs_by_run[run_id])

    def artifact(self, repository, artifact_id):
        self.calls.append(("artifact", artifact_id))
        value = self.exact[artifact_id]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    def download(self, repository, artifact_id):
        self.calls.append(("download", artifact_id))
        value = self.zips[artifact_id]
        if isinstance(value, Exception):
            raise value
        return value


def _resolve(api: FakeApi, tmp_path: Path, *, event="pull_request", ref="refs/pull/1/merge"):
    return resolver.resolve(
        api=api,
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        workflow_id=WORKFLOW_ID,
        workflow_path=resolver.CI_WORKFLOW_PATH,
        workflow_name="ci",
        artifact_name=ARTIFACT_NAME,
        output=tmp_path / "baseline.json",
        provenance_output=tmp_path / "provenance.json",
        event_name=event,
        ref=ref,
        now=NOW,
    )


def test_producer_schema_binds_run_attempt_and_sha(monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", str(RUN_ID))
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", str(RUN_ATTEMPT))
    monkeypatch.setenv("GITHUB_SHA", HEAD_SHA)
    arguments = producer.argparse.Namespace(iterations=2, warmups=1)
    report = producer.base_report(arguments)
    assert report["schemaVersion"] == 2
    assert report["producer"] == {"runId": RUN_ID, "runAttempt": RUN_ATTEMPT}
    assert report["candidate"]["localGitRevision"] == HEAD_SHA


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    (
        ("GITHUB_RUN_ID", "", "GITHUB_RUN_ID"),
        ("GITHUB_RUN_ATTEMPT", "0", "GITHUB_RUN_ATTEMPT"),
        ("GITHUB_SHA", "ABC", "GITHUB_SHA"),
    ),
)
def test_producer_rejects_missing_or_invalid_identity(monkeypatch, variable, value, message):
    monkeypatch.setenv("GITHUB_RUN_ID", str(RUN_ID))
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", str(RUN_ATTEMPT))
    monkeypatch.setenv("GITHUB_SHA", HEAD_SHA)
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError, match=message):
        producer.base_report(producer.argparse.Namespace(iterations=2, warmups=1))


def test_performance_comparator_keeps_three_x_regression_and_missing_metric_gate():
    latency = comparator.compare({"query": 1.0}, {"query": 3.01}, 3.0, False)
    throughput = comparator.compare({"rate": 3.0}, {"rate": 0.99}, 3.0, True)
    missing = comparator.compare({"query": 1.0}, {}, 3.0, False)
    assert latency[0]["status"] == "regression"
    assert throughput[0]["status"] == "regression"
    assert missing[0]["status"] == "missing"


def test_performance_comparator_rejects_reports_without_comparable_metrics(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    empty = {"schemaVersion": 2, "queries": []}
    baseline.write_text(json.dumps(empty), encoding="utf-8")
    candidate.write_text(json.dumps(empty), encoding="utf-8")
    monkeypatch.setattr(
        comparator.sys,
        "argv",
        [
            str(COMPARATOR_PATH),
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--max-regression",
            "3",
        ],
    )
    with pytest.raises(SystemExit, match="no comparable performance metrics"):
        comparator.main()


def test_resolver_downloads_exact_id_and_atomically_writes_bound_outputs(tmp_path):
    api = FakeApi()
    result = _resolve(api, tmp_path)
    assert result["mode"] == "comparison"
    assert result["run"] == {"id": RUN_ID, "attempt": RUN_ATTEMPT, "headSha": HEAD_SHA}
    assert result["artifact"]["id"] == ARTIFACT_ID
    assert result["artifact"]["restDigest"] == result["artifact"]["computedDigest"]
    assert json.loads((tmp_path / "baseline.json").read_text())["producer"]["runAttempt"] == 2
    assert json.loads((tmp_path / "provenance.json").read_text())["artifact"]["id"] == ARTIFACT_ID
    assert ("jobs", RUN_ID, RUN_ATTEMPT) in api.calls
    assert ("artifact", ARTIFACT_ID) in api.calls
    assert ("download", ARTIFACT_ID) in api.calls


def test_resolver_deduplicates_sorted_pages_and_uses_latest_valid_candidate(tmp_path):
    older = _artifact(4000, run_id=3000)
    older["created_at"] = "2026-07-01T00:00:00Z"
    duplicate = copy.deepcopy(older)
    api = FakeApi([older, _artifact(), duplicate])
    api.runs[3000] = _run(3000)
    api.jobs_by_run[3000] = [_job(3000)]
    api.exact[4000] = copy.deepcopy(older)
    api.zips[4000] = _zip(_report(run_id=3000))
    api._refresh_digests()
    artifacts = sorted(
        {artifact["id"]: artifact for artifact in api.enumerations[0]}.values(),
        key=lambda item: (item["created_at"], item["id"]),
        reverse=True,
    )
    api.enumerations = [artifacts]
    result = _resolve(api, tmp_path)
    assert result["artifact"]["id"] == ARTIFACT_ID


@pytest.mark.parametrize(
    "race",
    (
        "confirmed-expired-metadata",
        "within-expiry-safety-margin",
        "exact-download-404",
        "exact-download-410",
    ),
)
def test_allowed_race_loss_falls_back_to_older_exact_id(tmp_path, race):
    newest = _artifact(4002, run_id=3002)
    newest["created_at"] = "2026-08-02T00:00:00Z"
    older = _artifact(4000, run_id=3000)
    older["created_at"] = "2026-08-01T00:00:00Z"
    api = FakeApi([newest, older])
    api.runs.update({3002: _run(3002), 3000: _run(3000)})
    api.jobs_by_run.update({3002: [_job(3002)], 3000: [_job(3000)]})
    api.exact = {4002: copy.deepcopy(newest), 4000: copy.deepcopy(older)}
    api.zips = {
        4002: _zip(_report(run_id=3002)),
        4000: _zip(_report(run_id=3000)),
    }
    api._refresh_digests()

    if race == "confirmed-expired-metadata":
        api.exact[4002]["expired"] = True
    elif race == "within-expiry-safety-margin":
        api.exact[4002]["expires_at"] = (NOW + resolver.SAFETY_MARGIN).isoformat()
    elif race == "exact-download-404":
        api.zips[4002] = resolver.RaceLost("exact artifact download returned HTTP 404")
    elif race == "exact-download-410":
        api.zips[4002] = resolver.RaceLost("exact artifact download returned HTTP 410")
    else:
        raise AssertionError(f"unknown race scenario: {race}")

    result = _resolve(api, tmp_path)

    assert result["mode"] == "comparison"
    assert result["artifact"]["id"] == 4000
    assert json.loads((tmp_path / "provenance.json").read_text())["artifact"]["id"] == 4000
    assert json.loads((tmp_path / "baseline.json").read_text())["producer"]["runId"] == 3000
    if race.startswith("exact-download"):
        assert ("download", 4002) in api.calls
    else:
        assert ("download", 4002) not in api.calls


def test_digest_payload_or_zip_error_fails_closed_without_fallback(tmp_path):
    newer = _artifact()
    older = _artifact(4000, run_id=3000)
    api = FakeApi([newer, older])
    api.runs[3000] = _run(3000)
    api.jobs_by_run[3000] = [_job(3000)]
    api.exact[4000] = copy.deepcopy(older)
    api.zips[4000] = _zip(_report(run_id=3000))
    api.exact[ARTIFACT_ID]["digest"] = "sha256:" + "f" * 64
    with pytest.raises(resolver.BaselineError, match="does not match REST digest"):
        _resolve(api, tmp_path)
    assert ("run", 3000) not in api.calls


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("fork", "canonical repository"),
        ("pr", "run.event mismatch"),
        ("wrong-attempt", "baseline producer job run_attempt mismatch"),
        ("duplicate-job", "exactly one baseline producer"),
        ("artifact-sha", "artifact.workflow_run.head_sha mismatch"),
    ),
)
def test_untrusted_run_job_and_artifact_candidates_are_rejected(tmp_path, mutation, message):
    api = FakeApi()
    if mutation == "fork":
        api.runs[RUN_ID]["head_repository"]["id"] += 1
    elif mutation == "pr":
        api.runs[RUN_ID]["event"] = "pull_request"
    elif mutation == "wrong-attempt":
        api.jobs_by_run[RUN_ID][0]["run_attempt"] += 1
    elif mutation == "duplicate-job":
        api.jobs_by_run[RUN_ID].append(copy.deepcopy(api.jobs_by_run[RUN_ID][0]))
    elif mutation == "artifact-sha":
        api.exact[ARTIFACT_ID]["workflow_run"]["head_sha"] = "b" * 40
    with pytest.raises(resolver.BaselineError, match=message):
        _resolve(api, tmp_path)


def test_latest_bad_provenance_does_not_fall_back_to_older_valid_baseline(tmp_path):
    newer = _artifact()
    older = _artifact(4000, run_id=3000)
    older["created_at"] = "2026-07-01T00:00:00Z"
    api = FakeApi([newer, older])
    api.runs[3000] = _run(3000)
    api.jobs_by_run[3000] = [_job(3000, 5000)]
    api.exact[4000] = copy.deepcopy(older)
    api.zips[4000] = _zip(_report(run_id=3000))
    api.enumerations[0][0]["workflow_run"]["head_sha"] = "b" * 40
    api._refresh_digests()

    with pytest.raises(resolver.BaselineError, match="artifact.workflow_run.head_sha mismatch"):
        _resolve(api, tmp_path)
    assert ("run", 3000) not in api.calls


def test_latest_bad_provenance_never_bootstraps_on_main(tmp_path):
    api = FakeApi()
    api.runs[RUN_ID]["event"] = "pull_request"

    with pytest.raises(resolver.BaselineError, match="run.event mismatch"):
        _resolve(api, tmp_path, event="push", ref="refs/heads/main")
    assert sum(call[0] == "artifacts" for call in api.calls) == 1


def test_not_yet_completed_producer_can_fall_back_to_older_valid_baseline(tmp_path):
    newer = _artifact()
    older = _artifact(4000, run_id=3000)
    older["created_at"] = "2026-07-01T00:00:00Z"
    api = FakeApi([newer, older])
    api.runs[RUN_ID]["status"] = "in_progress"
    api.runs[RUN_ID]["conclusion"] = None
    api.runs[3000] = _run(3000)
    api.jobs_by_run[3000] = [_job(3000, 5000)]
    api.exact[4000] = copy.deepcopy(older)
    api.zips[4000] = _zip(_report(run_id=3000))
    api._refresh_digests()

    result = _resolve(api, tmp_path)
    assert result["artifact"]["id"] == 4000


@pytest.mark.parametrize("workflow_conclusion", ("failure", "cancelled"))
def test_downstream_workflow_terminal_state_keeps_successful_producer_trusted(
    tmp_path, workflow_conclusion
):
    api = FakeApi()
    api.runs[RUN_ID]["conclusion"] = workflow_conclusion

    result = _resolve(api, tmp_path)

    assert result["artifact"]["id"] == ARTIFACT_ID


def test_failed_baseline_producer_can_fall_back_to_older_valid_baseline(tmp_path):
    newer = _artifact()
    older = _artifact(4000, run_id=3000)
    older["created_at"] = "2026-07-01T00:00:00Z"
    api = FakeApi([newer, older])
    api.runs[RUN_ID]["conclusion"] = "failure"
    api.jobs_by_run[RUN_ID][0]["conclusion"] = "failure"
    api.runs[3000] = _run(3000)
    api.jobs_by_run[3000] = [_job(3000, 5000)]
    api.exact[4000] = copy.deepcopy(older)
    api.zips[4000] = _zip(_report(run_id=3000))
    api._refresh_digests()

    result = _resolve(api, tmp_path)
    assert result["artifact"]["id"] == 4000


def test_stable_failed_baseline_producer_allows_canonical_main_bootstrap(tmp_path):
    failed = _artifact()
    api = FakeApi([failed])
    api.enumerations = [[copy.deepcopy(failed)], [copy.deepcopy(failed)]]
    api.runs[RUN_ID]["conclusion"] = "failure"
    api.jobs_by_run[RUN_ID][0]["conclusion"] = "failure"

    result = _resolve(api, tmp_path, event="push", ref="refs/heads/main")

    assert result["mode"] == "bootstrap"
    assert result["enumeratedArtifactIds"] == [ARTIFACT_ID]
    assert sum(call[0] == "artifacts" for call in api.calls) == 2


def test_only_canonical_main_can_bootstrap_after_two_stable_complete_enumerations(tmp_path):
    api = FakeApi([])
    api.enumerations = [[], []]
    result = _resolve(api, tmp_path, event="push", ref="refs/heads/main")
    assert result["mode"] == "bootstrap"
    assert "two complete stable enumerations" in result["message"]
    assert sum(call[0] == "artifacts" for call in api.calls) == 2
    assert not (tmp_path / "baseline.json").exists()


def test_new_valid_candidate_inserted_between_bootstrap_enumerations_is_compared(tmp_path):
    api = FakeApi([])
    api.enumerations = [[], [_artifact()]]
    result = _resolve(api, tmp_path, event="push", ref="refs/heads/main")
    assert result["mode"] == "comparison"
    assert result["artifact"]["id"] == ARTIFACT_ID
    assert sum(call[0] == "artifacts" for call in api.calls) == 2


@pytest.mark.parametrize(
    ("event", "ref"),
    (("pull_request", "refs/pull/1/merge"), ("schedule", "refs/heads/main"), ("push", "refs/heads/dev")),
)
def test_pr_and_noncanonical_contexts_never_bootstrap(tmp_path, event, ref):
    api = FakeApi([])
    api.enumerations = [[], []]
    with pytest.raises(resolver.BaselineError, match="bootstrap is forbidden"):
        _resolve(api, tmp_path, event=event, ref=ref)
    assert sum(call[0] == "artifacts" for call in api.calls) == 1


def test_unstable_enumeration_fails_closed(tmp_path):
    first = []
    second = [_artifact(expired=True)]
    third = [_artifact(4002, expired=True)]
    api = FakeApi([])
    api.enumerations = [first, second, third]
    with pytest.raises(resolver.BaselineError, match="not stable"):
        _resolve(api, tmp_path, event="push", ref="refs/heads/main")
    assert sum(call[0] == "artifacts" for call in api.calls) == 2


def test_null_workflow_id_fails_closed(tmp_path):
    trust = tmp_path / "trust.json"
    trust.write_text(
        json.dumps(
            {
                "schema_version": "trusted-workflow-ids/v1",
                "ci_workflow": {"path": resolver.CI_WORKFLOW_PATH, "name": "ci", "id": None},
            }
        )
    )
    with pytest.raises(resolver.BaselineError, match="not registered"):
        resolver.load_trust(trust)


@pytest.mark.parametrize(
    ("digest", "message"),
    ((None, "non-empty string"), ("md5:" + "0" * 32, "must use sha256"), ("sha256:ABC", "must use sha256")),
)
def test_digest_contract_is_strict(digest, message):
    artifact = _artifact()
    artifact["digest"] = digest
    with pytest.raises(resolver.BaselineError, match=message):
        resolver.validate_artifact_metadata(
            artifact,
            artifact_name=ARTIFACT_NAME,
            repository_id=REPOSITORY_ID,
            run_id=RUN_ID,
            head_sha=HEAD_SHA,
            now=NOW,
        )


def test_zip_rejects_extra_member_symlink_and_oversize():
    extra = io.BytesIO()
    with zipfile.ZipFile(extra, "w") as archive:
        archive.writestr(resolver.BASELINE_MEMBER, "{}")
        archive.writestr("extra", "{}")
    with pytest.raises(resolver.BaselineError, match="exactly one"):
        resolver.extract_report(extra.getvalue())

    link = io.BytesIO()
    with zipfile.ZipFile(link, "w") as archive:
        info = zipfile.ZipInfo(resolver.BASELINE_MEMBER)
        info.external_attr = (0o120777 << 16)
        archive.writestr(info, "target")
    with pytest.raises(resolver.BaselineError, match="regular file"):
        resolver.extract_report(link.getvalue())

    huge = io.BytesIO()
    with zipfile.ZipFile(huge, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(resolver.BASELINE_MEMBER, b"x" * (resolver.MAX_REPORT_BYTES + 1))
    with pytest.raises(resolver.BaselineError, match="size limit"):
        resolver.extract_report(huge.getvalue())


def test_json_duplicate_keys_and_payload_provenance_mismatch_fail_closed():
    with pytest.raises(resolver.BaselineError, match="duplicate key"):
        resolver._json_no_duplicates(b'{"schemaVersion":2,"schemaVersion":2}', "report")
    payload = _report(run_attempt=RUN_ATTEMPT + 1)
    with pytest.raises(resolver.BaselineError, match="producer run identity mismatch"):
        resolver.validate_report(
            json.dumps(payload).encode(), run_id=RUN_ID, run_attempt=RUN_ATTEMPT, head_sha=HEAD_SHA
        )


def test_freshness_uses_real_expires_at_threshold():
    api = FakeApi()
    result = resolver.freshness(
        api=api,
        repository=REPOSITORY,
        repository_id=REPOSITORY_ID,
        workflow_id=WORKFLOW_ID,
        workflow_path=resolver.CI_WORKFLOW_PATH,
        workflow_name="ci",
        artifact_name=ARTIFACT_NAME,
        now=NOW,
        threshold=timedelta(days=14),
    )
    assert result["fresh"] is True
    api.exact[ARTIFACT_ID]["expires_at"] = (NOW + timedelta(days=13)).isoformat()
    api.enumerations[0][0]["expires_at"] = api.exact[ARTIFACT_ID]["expires_at"]
    with pytest.raises(resolver.BaselineError, match="below freshness threshold"):
        resolver.freshness(
            api=api,
            repository=REPOSITORY,
            repository_id=REPOSITORY_ID,
            workflow_id=WORKFLOW_ID,
            workflow_path=resolver.CI_WORKFLOW_PATH,
            workflow_name="ci",
            artifact_name=ARTIFACT_NAME,
            now=NOW,
            threshold=timedelta(days=14),
        )


class RecordingApi(resolver.GitHubApi):
    def __init__(self, responses):
        super().__init__("secret-token")
        self.responses = iter(responses)
        self.seen: list[tuple[str, dict[str, str]]] = []

    def _send(self, url, headers):
        self.seen.append((url, dict(headers)))
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return value


def _api_json_response(payload, *, link=None):
    headers = {} if link is None else {"Link": link}
    return resolver.RawResponse(200, headers, json.dumps(payload).encode())


def _enumerate_collection(api, collection):
    if collection == "artifacts":
        return api.artifacts(REPOSITORY, ARTIFACT_NAME)
    return api.jobs(REPOSITORY, RUN_ID, RUN_ATTEMPT)


def test_artifact_and_attempt_job_pagination_reach_link_end_and_sort():
    older = _artifact(4000, run_id=3000)
    older["created_at"] = "2026-07-01T00:00:00Z"
    newer = _artifact()
    artifact_api = RecordingApi(
        [
            _api_json_response(
                {"total_count": 2, "artifacts": [older]},
                link=(
                    '<https://api.github.com/repos/example/project/actions/artifacts?'
                    'name=db-postgres-performance-baseline-main&per_page=100&page=2>; rel="next"'
                ),
            ),
            _api_json_response({"total_count": 2, "artifacts": [newer]}),
        ]
    )
    artifacts = artifact_api.artifacts(REPOSITORY, ARTIFACT_NAME)
    assert [artifact["id"] for artifact in artifacts] == [ARTIFACT_ID, 4000]
    assert all(f"name={ARTIFACT_NAME}" in url for url, _ in artifact_api.seen)

    job_api = RecordingApi(
        [
            _api_json_response(
                {"total_count": 2, "jobs": [{"id": 5000, "name": "other"}]},
                link=(
                    f'<https://api.github.com/repos/example/project/actions/runs/{RUN_ID}/'
                    f'attempts/{RUN_ATTEMPT}/jobs?per_page=100&page=2>; rel="next"'
                ),
            ),
            _api_json_response({"total_count": 2, "jobs": [_job()]}),
        ]
    )
    jobs = job_api.jobs(REPOSITORY, RUN_ID, RUN_ATTEMPT)
    resolver.validate_jobs(jobs, run_id=RUN_ID, run_attempt=RUN_ATTEMPT, head_sha=HEAD_SHA)
    assert len(job_api.seen) == 2


def test_pagination_cap_and_partial_page_failure_cannot_bootstrap():
    responses = []
    for page in range(1, resolver.MAX_PAGES + 1):
        responses.append(
            _api_json_response(
                {"total_count": 1, "artifacts": []},
                link=(
                    '<https://api.github.com/repos/example/project/actions/artifacts?'
                    f'name={ARTIFACT_NAME}&per_page=100&page={page + 1}>; rel="next"'
                ),
            )
        )
    capped = RecordingApi(responses)
    with pytest.raises(resolver.BaselineError, match="coverage incomplete"):
        capped.artifacts(REPOSITORY, ARTIFACT_NAME)
    assert len(capped.seen) == resolver.MAX_PAGES

    partial = RecordingApi(
        [
            _api_json_response(
                {"total_count": 1, "artifacts": []},
                link=(
                    '<https://api.github.com/repos/example/project/actions/artifacts?'
                    f'name={ARTIFACT_NAME}&per_page=100&page=2>; rel="next"'
                ),
            ),
            ConnectionError("connection reset"),
        ]
    )
    with pytest.raises(resolver.BaselineError, match="request failed"):
        partial.artifacts(REPOSITORY, ARTIFACT_NAME)


@pytest.mark.parametrize("collection", ("artifacts", "jobs"))
def test_missing_pagination_link_with_uncollected_total_fails_closed(collection):
    if collection == "artifacts":
        api = RecordingApi(
            [_api_json_response({"total_count": 2, "artifacts": [_artifact()]})]
        )
    else:
        api = RecordingApi([_api_json_response({"total_count": 2, "jobs": [_job()]})])

    with pytest.raises(resolver.BaselineError, match="coverage incomplete"):
        _enumerate_collection(api, collection)


@pytest.mark.parametrize("collection", ("artifacts", "jobs"))
def test_pagination_total_count_drift_fails_closed(collection):
    if collection == "artifacts":
        first_payload = {"total_count": 2, "artifacts": [_artifact()]}
        second_payload = {"total_count": 3, "artifacts": [_artifact(4000, run_id=3000)]}
        path = (
            "https://api.github.com/repos/example/project/actions/artifacts?"
            f"name={ARTIFACT_NAME}&per_page=100&page=2"
        )
    else:
        first_payload = {"total_count": 2, "jobs": [_job()]}
        second_payload = {"total_count": 3, "jobs": [_job(job_id=5000)]}
        path = (
            f"https://api.github.com/repos/example/project/actions/runs/{RUN_ID}/"
            f"attempts/{RUN_ATTEMPT}/jobs?per_page=100&page=2"
        )
    api = RecordingApi(
        [
            _api_json_response(first_payload, link=f'<{path}>; rel="next"'),
            _api_json_response(second_payload),
        ]
    )

    with pytest.raises(resolver.BaselineError, match="total_count changed"):
        _enumerate_collection(api, collection)


@pytest.mark.parametrize("collection", ("artifacts", "jobs"))
def test_duplicate_pagination_record_fails_closed(collection):
    if collection == "artifacts":
        first_payload = {"total_count": 2, "artifacts": [_artifact()]}
        second_payload = {"total_count": 2, "artifacts": [copy.deepcopy(_artifact())]}
        path = (
            "https://api.github.com/repos/example/project/actions/artifacts?"
            f"name={ARTIFACT_NAME}&per_page=100&page=2"
        )
    else:
        first_payload = {"total_count": 2, "jobs": [_job()]}
        second_payload = {"total_count": 2, "jobs": [copy.deepcopy(_job())]}
        path = (
            f"https://api.github.com/repos/example/project/actions/runs/{RUN_ID}/"
            f"attempts/{RUN_ATTEMPT}/jobs?per_page=100&page=2"
        )
    api = RecordingApi(
        [
            _api_json_response(first_payload, link=f'<{path}>; rel="next"'),
            _api_json_response(second_payload),
        ]
    )

    with pytest.raises(resolver.BaselineError, match="duplicate .* ID"):
        _enumerate_collection(api, collection)


def test_pagination_requires_total_count_on_every_page():
    artifact_api = RecordingApi([_api_json_response({"artifacts": []})])
    with pytest.raises(resolver.BaselineError, match="total_count"):
        artifact_api.artifacts(REPOSITORY, ARTIFACT_NAME)

    job_api = RecordingApi([_api_json_response({"jobs": []})])
    with pytest.raises(resolver.BaselineError, match="total_count"):
        job_api.jobs(REPOSITORY, RUN_ID, RUN_ATTEMPT)


def test_cross_host_redirect_strips_all_github_headers_and_same_host_retains_allowlist():
    cross = RecordingApi(
        [
            resolver.RawResponse(302, {"Location": "https://storage.example/object"}, b""),
            resolver.RawResponse(200, {}, b"zip"),
        ]
    )
    assert cross.download(REPOSITORY, ARTIFACT_ID) == b"zip"
    assert "Authorization" in cross.seen[0][1]
    assert cross.seen[1][1] == {}

    same = RecordingApi(
        [
            resolver.RawResponse(302, {"Location": "https://api.github.com/storage"}, b""),
            resolver.RawResponse(200, {}, b"zip"),
        ]
    )
    same.download(REPOSITORY, ARTIFACT_ID)
    assert set(same.seen[1][1]) == {
        "Accept",
        "Authorization",
        "X-GitHub-Api-Version",
        "User-Agent",
    }


def test_exact_metadata_5xx_retries_same_id_but_403_and_404_do_not():
    metadata = _artifact()
    retried = RecordingApi(
        [
            resolver.RawResponse(503, {}, b""),
            resolver.RawResponse(200, {}, json.dumps(metadata).encode()),
        ]
    )
    assert retried.artifact(REPOSITORY, ARTIFACT_ID)["id"] == ARTIFACT_ID
    assert len(retried.seen) == 2
    assert len({url for url, _ in retried.seen}) == 1

    forbidden = RecordingApi([resolver.RawResponse(403, {}, b"")])
    with pytest.raises(resolver.BaselineError, match="HTTP 403"):
        forbidden.artifact(REPOSITORY, ARTIFACT_ID)
    assert len(forbidden.seen) == 1

    missing = RecordingApi([resolver.RawResponse(410, {}, b"")])
    with pytest.raises(resolver.RaceLost, match="HTTP 410"):
        missing.artifact(REPOSITORY, ARTIFACT_ID)
    assert len(missing.seen) == 1


def test_download_403_is_fatal_5xx_retries_same_id_and_404_is_race_lost():
    forbidden = RecordingApi([resolver.RawResponse(403, {}, b"")])
    with pytest.raises(resolver.BaselineError, match="HTTP 403"):
        forbidden.download(REPOSITORY, ARTIFACT_ID)
    assert len(forbidden.seen) == 1

    retry = RecordingApi(
        [
            resolver.RawResponse(503, {}, b""),
            resolver.RawResponse(502, {}, b""),
            resolver.RawResponse(200, {}, b"zip"),
        ]
    )
    assert retry.download(REPOSITORY, ARTIFACT_ID) == b"zip"
    assert len(retry.seen) == 3
    assert len({url for url, _ in retry.seen}) == 1

    missing = RecordingApi([resolver.RawResponse(404, {}, b"")])
    with pytest.raises(resolver.RaceLost, match="HTTP 404"):
        missing.download(REPOSITORY, ARTIFACT_ID)

    exhausted = RecordingApi([resolver.RawResponse(503, {}, b"")] * 3)
    with pytest.raises(resolver.BaselineError, match="3 same-ID attempts"):
        exhausted.download(REPOSITORY, ARTIFACT_ID)
    assert len(exhausted.seen) == 3


def test_download_rejects_http_and_excessive_redirects():
    insecure = RecordingApi(
        [resolver.RawResponse(302, {"Location": "http://storage.example/object"}, b"")]
    )
    with pytest.raises(resolver.BaselineError, match="must use HTTPS"):
        insecure.download(REPOSITORY, ARTIFACT_ID)

    redirects = [
        resolver.RawResponse(
            302,
            {"Location": f"https://storage.example/object-{index}"},
            b"",
        )
        for index in range(resolver.MAX_REDIRECTS + 1)
    ]
    excessive = RecordingApi(redirects)
    with pytest.raises(resolver.BaselineError, match="redirect limit"):
        excessive.download(REPOSITORY, ARTIFACT_ID)
    assert len(excessive.seen) == resolver.MAX_REDIRECTS + 1


def _minimal_zip_with_method(method: int) -> bytes:
    name = resolver.BASELINE_MEMBER.encode()
    data = b"{}"
    crc = 0
    local = struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, 0, method, 0, 0, crc, len(data), len(data), len(name), 0)
    central = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        20,
        20,
        0,
        method,
        0,
        0,
        crc,
        len(data),
        len(data),
        len(name),
        0,
        0,
        0,
        0,
        0,
        0,
    )
    body = local + name + data
    directory = central + name
    end = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(directory), len(body), 0)
    return body + directory + end


def test_zip_rejects_unknown_compression_method():
    with pytest.raises(resolver.BaselineError, match="unsupported compression"):
        resolver.extract_report(_minimal_zip_with_method(99))

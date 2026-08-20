"""Behavioral contract tests for trusted shared-edge receipt persistence."""

import base64
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/validate-trusted-shared-edge-receipts.py"
SPEC = importlib.util.spec_from_file_location("trusted_shared_edge_receipts", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

OPERATION_SHA = "a" * 40
PREVIOUS_SHA = "b" * 40


def _receipt(phase: str, runtime: str, status: str = "success") -> dict:
    receipt = {
        "contractVersion": 1,
        "owner": {"project": "rss", "repo": "blankhoney/reno_rss"},
        "operation": {"fullSha": OPERATION_SHA},
        "workflowRun": 123,
        "phase": phase,
        "runtime": {"fullSha": runtime},
        "rollback": {"rollbackFrom": None, "target": None},
        "timestamp": "2026-08-20T00:00:00Z",
        "overallStatus": status,
        "urls": [
            {
                "name": "blog-public",
                "configuredURL": "https://blog.blankhoney.xyz/zh",
                "status": 200,
                "finalURL": "https://blog.blankhoney.xyz/zh",
                "tls": True,
                "redirect": False,
                "result": "success",
                "error": None,
            },
            {
                "name": "blog-public-status",
                "configuredURL": "https://blog.blankhoney.xyz/api/status",
                "status": 200,
                "finalURL": "https://blog.blankhoney.xyz/api/status",
                "tls": True,
                "redirect": False,
                "result": "success",
                "error": None,
            },
            {
                "name": "rss-production-auth",
                "configuredURL": "https://ai-reader.blankhoney.xyz/",
                "status": 200,
                "finalURL": "https://auth.blankhoney.xyz/",
                "tls": True,
                "redirect": True,
                "result": "success",
                "error": None,
            },
        ],
        "edge": {
            "caddyContainer": "myrss-edge-caddy-1",
            "myrssAppAttached": True,
            "brianstormEdgeAttached": True,
            "networkDriver": "bridge",
            "configLoaded": True,
            "rssUpstreamReachable": True,
            "blogUpstreamReachable": True,
            "result": "success",
            "error": None,
        },
    }
    if phase in {"post-rollback", "post-compensation"}:
        receipt["rollback"] = {"rollbackFrom": PREVIOUS_SHA, "target": OPERATION_SHA}
    if status == "failure":
        receipt["urls"][0].update(
            {"status": 503, "result": "failure", "error": "unexpected_status"}
        )
        receipt["edge"].update({"result": "failure", "error": ["public_probe_failed"]})
    return receipt


def _frame(phase: str, runtime: str, status: str = "success") -> str:
    payload = json.dumps(_receipt(phase, runtime, status), separators=(",", ":")).encode()
    return f"TRUSTED_SHARED_EDGE_RECEIPT {phase} {base64.b64encode(payload).decode()}"


def _arguments(stdout: Path, receipts: Path, expectation: str = "success") -> list[str]:
    return [
        "--stdout",
        str(stdout),
        "--receipt-dir",
        str(receipts),
        "--operation-sha",
        OPERATION_SHA,
        "--workflow-run",
        "123",
        "--request-type",
        "deploy",
        "--expect",
        expectation,
    ]


def test_persists_only_strict_current_operation_receipts(tmp_path):
    stdout = tmp_path / "ssh.stdout"
    stdout.write_text(
        "\n".join(
            (
                "ordinary remote log is not an artifact",
                _frame("pre-mutation", PREVIOUS_SHA),
                _frame("pre-activation", PREVIOUS_SHA),
                _frame("post-activation", OPERATION_SHA),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    receipt_dir = tmp_path / "receipts"

    assert validator.main(_arguments(stdout, receipt_dir)) == 0
    assert sorted(path.name for path in receipt_dir.iterdir()) == [
        "post-activation.json",
        "pre-activation.json",
        "pre-mutation.json",
    ]
    assert "ordinary remote log" not in "\n".join(
        path.read_text(encoding="utf-8") for path in receipt_dir.iterdir()
    )


def test_rejects_unknown_and_duplicate_frames_and_missing_compensation(tmp_path):
    stdout = tmp_path / "ssh.stdout"
    stdout.write_text(
        "\n".join(
            (
                _frame("pre-mutation", PREVIOUS_SHA),
                _frame("pre-mutation", PREVIOUS_SHA),
                "TRUSTED_SHARED_EDGE_RECEIPT unknown Zm9v",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    assert validator.main(_arguments(stdout, tmp_path / "receipts", "compensation")) == 1


def test_rejects_existing_output_and_wrong_request_final_phase(tmp_path):
    stdout = tmp_path / "ssh.stdout"
    stdout.write_text(
        "\n".join(
            (
                _frame("pre-mutation", PREVIOUS_SHA),
                _frame("pre-activation", PREVIOUS_SHA),
                _frame("post-rollback", OPERATION_SHA),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    existing = tmp_path / "existing"
    existing.mkdir()
    assert validator.main(_arguments(stdout, existing)) == 1

    fresh = tmp_path / "fresh"
    assert validator.main(_arguments(stdout, fresh)) == 1


def test_persists_strict_early_compensation_without_fake_pre_activation(tmp_path):
    stdout = tmp_path / "ssh.stdout"
    stdout.write_text(
        "\n".join(
            (
                _frame("pre-mutation", PREVIOUS_SHA),
                _frame("post-compensation", PREVIOUS_SHA),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    receipt_dir = tmp_path / "receipts"
    assert validator.main(_arguments(stdout, receipt_dir, "compensation")) == 0
    assert sorted(path.name for path in receipt_dir.iterdir()) == [
        "post-compensation.json",
        "pre-mutation.json",
    ]


def test_persists_authenticated_pre_mutation_failure_without_fake_compensation(tmp_path):
    stdout = tmp_path / "ssh.stdout"
    stdout.write_text(_frame("pre-mutation", PREVIOUS_SHA, "failure") + "\n", encoding="utf-8")
    receipt_dir = tmp_path / "receipts"
    assert validator.main(_arguments(stdout, receipt_dir, "compensation")) == 0
    assert [path.name for path in receipt_dir.iterdir()] == ["pre-mutation.json"]

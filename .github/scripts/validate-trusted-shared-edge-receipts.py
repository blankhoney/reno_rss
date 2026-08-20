#!/usr/bin/env python3
"""Persist only cross-repository v1 receipts verified by the canonical verifier."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


FRAME_PREFIX = "TRUSTED_SHARED_EDGE_RECEIPT "
PHASES = frozenset(
    ("pre-mutation", "pre-activation", "post-activation", "post-rollback", "post-compensation")
)
SHA = re.compile(r"[0-9a-f]{40}")
VERIFIER = Path(__file__).resolve().parents[2] / "infra/deploy/verify-shared-edge-receipt.mjs"


def reject(message: str) -> None:
    raise ValueError(message)


def mapping(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        reject(f"{label} must be an object")
    return value


def full_sha(value: object, label: str) -> str:
    if type(value) is not str or SHA.fullmatch(value) is None:
        reject(f"{label} must be a 40-character lowercase SHA")
    return value


def validate_receipt(
    receipt: object,
    *,
    operation_sha: str,
    workflow_run: int,
    phase: str,
    payload: bytes | None = None,
) -> dict[str, Any]:
    item = mapping(receipt, "receipt")
    if payload is None:
        payload = json.dumps(item, separators=(",", ":")).encode()
    status = item.get("overallStatus")
    if status not in {"success", "failure"}:
        reject("receipt overallStatus is invalid")
    runtime = mapping(item.get("runtime"), "runtime")
    runtime_sha = full_sha(runtime.get("fullSha"), "runtime.fullSha")
    verifier_args = [
        "node", str(VERIFIER), "", status, "rss", "blankhoney/reno_rss",
        operation_sha, runtime_sha, str(workflow_run), phase,
    ]
    if phase in {"post-rollback", "post-compensation"}:
        rollback = mapping(item.get("rollback"), "rollback")
        verifier_args.extend((
            full_sha(rollback.get("rollbackFrom"), "rollback.rollbackFrom"),
            full_sha(rollback.get("target"), "rollback.target"),
        ))
    with tempfile.NamedTemporaryFile(prefix="shared-edge-receipt-", mode="xb", delete=False) as output:
        output.write(payload)
        receipt_path = Path(output.name)
    try:
        os.chmod(receipt_path, 0o600)
        verifier_args[2] = str(receipt_path)
        result = subprocess.run(verifier_args, stdin=subprocess.DEVNULL, capture_output=True, check=False)
        if result.returncode != 0:
            reject("receipt failed the canonical shared-edge verifier")
    finally:
        receipt_path.unlink(missing_ok=True)
    return item


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--stdout", type=Path, required=True)
    result.add_argument("--receipt-dir", type=Path, required=True)
    result.add_argument("--operation-sha", required=True)
    result.add_argument("--workflow-run", required=True)
    result.add_argument("--request-type", choices=("deploy", "rollback"), required=True)
    result.add_argument("--expect", choices=("success", "compensation"), required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        operation_sha = full_sha(args.operation_sha, "operation SHA")
        if not args.workflow_run.isdigit() or int(args.workflow_run) <= 0:
            reject("workflow run must be positive")
        workflow_run = int(args.workflow_run)
        raw = args.stdout.read_text(encoding="utf-8", errors="strict")
        frames: dict[str, dict[str, Any]] = {}
        for line in raw.splitlines():
            if not line.startswith(FRAME_PREFIX):
                continue
            parts = line.split(" ")
            if len(parts) != 3 or parts[0] != "TRUSTED_SHARED_EDGE_RECEIPT":
                reject("malformed shared-edge receipt frame")
            phase, encoded = parts[1:]
            if phase not in PHASES or phase in frames:
                reject("shared-edge receipt phase is unknown or duplicated")
            try:
                payload = base64.b64decode(encoded, validate=True)
                receipt = json.loads(payload.decode("utf-8"))
            except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
                reject("shared-edge receipt frame payload is invalid")
            frames[phase] = validate_receipt(
                receipt,
                operation_sha=operation_sha,
                workflow_run=workflow_run,
                phase=phase,
                payload=payload,
            )

        final = "post-activation" if args.request_type == "deploy" else "post-rollback"
        if args.expect == "success":
            expected_phases = {"pre-mutation", "pre-activation", final}
            if set(frames) != expected_phases or any(
                receipt["overallStatus"] != "success" for receipt in frames.values()
            ):
                reject("successful transaction receipt set is invalid")
        elif set(frames) == {"pre-mutation"}:
            if frames["pre-mutation"]["overallStatus"] != "failure":
                reject("pre-mutation-only outcome must be an authenticated failure")
        else:
            expected_phases = {"pre-mutation", "post-compensation"}
            if "pre-activation" in frames:
                expected_phases.add("pre-activation")
                if final in frames:
                    expected_phases.add(final)
            if set(frames) != expected_phases:
                reject("compensated transaction receipt set is invalid")
            if frames["post-compensation"]["overallStatus"] != "success":
                reject("post-compensation receipt must be successful")

        pre_runtime = frames["pre-mutation"]["runtime"]["fullSha"]
        if "pre-activation" in frames and pre_runtime != frames["pre-activation"]["runtime"]["fullSha"]:
            reject("pre-mutation and pre-activation runtime must match")
        if pre_runtime == operation_sha:
            reject("pre-activation runtime must differ from operation")
        for rollback_phase in ("post-rollback", "post-compensation"):
            if rollback_phase in frames:
                rollback = frames[rollback_phase]["rollback"]
                if rollback["rollbackFrom"] != pre_runtime or rollback["target"] != operation_sha:
                    reject("rollback receipt must bind actual pre-runtime and operation")

        if args.receipt_dir.exists() or args.receipt_dir.is_symlink():
            reject("receipt directory must be a fresh non-symbolic output directory")
        args.receipt_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        for phase, receipt in frames.items():
            destination = args.receipt_dir / f"{phase}.json"
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

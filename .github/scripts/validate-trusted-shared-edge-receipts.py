#!/usr/bin/env python3
"""Persist and validate only signed-shape shared-edge receipts from SSH stdout."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse


FRAME_PREFIX = "TRUSTED_SHARED_EDGE_RECEIPT "
PHASES = frozenset(
    ("pre-mutation", "pre-activation", "post-activation", "post-rollback", "post-compensation")
)
SHA = re.compile(r"[0-9a-f]{40}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
RSS_URL = "https://ai-reader.blankhoney.xyz/"
BLOG_URL = "https://blog.blankhoney.xyz/zh"


def reject(message: str) -> None:
    raise ValueError(message)


def mapping(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        reject(f"{label} must be an object")
    return value


def exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        reject(f"{label} has unexpected keys")


def full_sha(value: object, label: str) -> str:
    if type(value) is not str or SHA.fullmatch(value) is None:
        reject(f"{label} must be a 40-character lowercase SHA")
    return value


def final_https(value: object, allowed_hosts: set[str], label: str) -> None:
    if type(value) is not str:
        reject(f"{label} must be a URL")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        reject(f"{label} is outside the fixed HTTPS allowlist")


def validate_urls(value: object) -> None:
    if type(value) is not list or len(value) != 2:
        reject("urls must contain exactly RSS and Blog results")
    indexed: dict[str, dict[str, Any]] = {}
    for item in value:
        result = mapping(item, "urls entry")
        exact_keys(result, {"name", "configuredURL", "status", "finalURL", "tls", "redirect"}, "url")
        name = result.get("name")
        if type(name) is not str or name in indexed:
            reject("urls must have unique names")
        indexed[name] = result
    if set(indexed) != {"rss", "blog"}:
        reject("urls must contain rss and blog")

    rss = indexed["rss"]
    if rss["configuredURL"] != RSS_URL or rss["status"] != 200 or rss["tls"] is not True:
        reject("RSS public result is invalid")
    final_https(rss["finalURL"], {"ai-reader.blankhoney.xyz", "auth.blankhoney.xyz"}, "RSS finalURL")
    redirect = mapping(rss["redirect"], "RSS redirect")
    exact_keys(redirect, {"required", "followed", "initialStatus", "initialURL"}, "RSS redirect")
    if redirect["required"] is not True or redirect["followed"] is not True:
        reject("RSS authentication redirect is missing")
    if type(redirect["initialStatus"]) is not int or not 300 <= redirect["initialStatus"] < 400:
        reject("RSS initial redirect status is invalid")
    final_https(redirect["initialURL"], {"ai-reader.blankhoney.xyz", "auth.blankhoney.xyz"}, "RSS initialURL")

    blog = indexed["blog"]
    if blog["configuredURL"] != BLOG_URL or blog["status"] != 200 or blog["tls"] is not True:
        reject("Blog public result is invalid")
    final_https(blog["finalURL"], {"blog.blankhoney.xyz"}, "Blog finalURL")
    redirect = mapping(blog["redirect"], "Blog redirect")
    exact_keys(redirect, {"required", "followed", "initialStatus", "initialURL"}, "Blog redirect")
    if (
        redirect["required"] is not False
        or redirect["followed"] is not False
        or redirect["initialStatus"] != 200
        or redirect["initialURL"] is not None
    ):
        reject("Blog redirect result is invalid")


def validate_edge(value: object) -> None:
    edge = mapping(value, "edge")
    exact_keys(
        edge,
        {
            "caddyContainer",
            "myrssAppAttached",
            "brianstormEdgeAttached",
            "networkDriver",
            "configLoaded",
            "rssUpstreamReachable",
            "blogUpstreamReachable",
            "productionBlogWebAttachedToProductionEdge",
            "stagingWebAttachedToProductionEdge",
        },
        "edge",
    )
    if edge["caddyContainer"] != "myrss-edge-caddy-1":
        reject("unexpected Caddy container")
    if any(
        edge[key] is not True
        for key in (
            "myrssAppAttached",
            "brianstormEdgeAttached",
            "configLoaded",
            "rssUpstreamReachable",
            "blogUpstreamReachable",
            "productionBlogWebAttachedToProductionEdge",
        )
    ) or edge["stagingWebAttachedToProductionEdge"] is not False:
        reject("shared edge membership or upstream result is invalid")
    drivers = mapping(edge["networkDriver"], "edge.networkDriver")
    exact_keys(drivers, {"myrssApp", "brianstormEdge"}, "edge.networkDriver")
    if drivers != {"myrssApp": "bridge", "brianstormEdge": "bridge"}:
        reject("shared edge network driver is invalid")


def validate_receipt(
    receipt: object, *, operation_sha: str, workflow_run: int, phase: str
) -> dict[str, Any]:
    item = mapping(receipt, "receipt")
    expected = {
        "contractVersion",
        "owner",
        "operation",
        "workflowRun",
        "phase",
        "runtime",
        "timestamp",
        "urls",
        "edge",
    }
    rollback_phase = phase in {"post-rollback", "post-compensation"}
    if rollback_phase:
        expected.add("rollback")
    exact_keys(item, expected, "receipt")
    if item["contractVersion"] != 1 or item["phase"] != phase:
        reject("receipt contract version or phase mismatch")
    owner = mapping(item["owner"], "owner")
    if owner != {"project": "rss", "repo": "blankhoney/reno_rss"}:
        reject("receipt owner is invalid")
    operation = mapping(item["operation"], "operation")
    if operation != {"fullSha": operation_sha}:
        reject("receipt operation does not match the trusted operation SHA")
    if type(item["workflowRun"]) is not int or item["workflowRun"] != workflow_run:
        reject("receipt workflowRun does not match the trusted workflow")
    runtime = mapping(item["runtime"], "runtime")
    exact_keys(runtime, {"fullSha"}, "runtime")
    runtime_sha = full_sha(runtime["fullSha"], "runtime.fullSha")
    if type(item["timestamp"]) is not str or TIMESTAMP.fullmatch(item["timestamp"]) is None:
        reject("receipt timestamp must be RFC3339 UTC")
    validate_urls(item["urls"])
    validate_edge(item["edge"])
    if phase == "post-activation" and runtime_sha != operation_sha:
        reject("post-activation runtime must equal operation")
    if rollback_phase:
        rollback = mapping(item["rollback"], "rollback")
        exact_keys(rollback, {"rollbackFrom", "target"}, "rollback")
        rollback_from = full_sha(rollback["rollbackFrom"], "rollback.rollbackFrom")
        target = full_sha(rollback["target"], "rollback.target")
        if target != operation_sha or rollback_from == target:
            reject("rollback target is invalid")
        required_runtime = target if phase == "post-rollback" else rollback_from
        if runtime_sha != required_runtime:
            reject("rollback runtime does not match its phase")
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
                receipt, operation_sha=operation_sha, workflow_run=workflow_run, phase=phase
            )
        required = {"pre-mutation", "pre-activation"}
        final = "post-activation" if args.request_type == "deploy" else "post-rollback"
        required.add(final if args.expect == "success" else "post-compensation")
        if not required.issubset(frames):
            reject("missing required shared-edge receipt phase")
        pre_runtime = frames["pre-mutation"]["runtime"]["fullSha"]
        if pre_runtime != frames["pre-activation"]["runtime"]["fullSha"]:
            reject("pre-mutation and pre-activation runtime must match")
        if pre_runtime == operation_sha:
            reject("pre-activation runtime must differ from operation")
        allowed = {"pre-mutation", "pre-activation", final}
        if args.expect == "compensation":
            allowed = {"pre-mutation", "pre-activation", "post-compensation"}
            allowed.add(final)
        if not set(frames).issubset(allowed):
            reject("receipt phase is not valid for the transaction outcome")
        for rollback_phase in ("post-rollback", "post-compensation"):
            if rollback_phase in frames:
                rollback = frames[rollback_phase]["rollback"]
                if rollback["rollbackFrom"] != pre_runtime or rollback["target"] != operation_sha:
                    reject("rollback receipt must bind the actual pre-activation runtime and operation")
        if args.receipt_dir.exists():
            reject("receipt directory must be a fresh output directory")
        if args.receipt_dir.is_symlink():
            reject("receipt directory must not be a symlink")
        args.receipt_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not args.receipt_dir.is_dir() or args.receipt_dir.is_symlink():
            reject("receipt directory is unsafe")
        for phase, receipt in frames.items():
            with (args.receipt_dir / f"{phase}.json").open("x", encoding="utf-8") as output:
                output.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

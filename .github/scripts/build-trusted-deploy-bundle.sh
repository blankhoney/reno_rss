#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build the secret-free manifest streamed directly into the locked VPS transaction.
set -euo pipefail

declare request_type='' environment='' owner_project='' owner_repo='' operation_sha='' control_plane_sha=''
declare workflow_run='' image_tag='' web_image='' api_image='' worker_image=''
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
die() { printf '%s\n' "trusted deploy bundle: $*" >&2; exit 64; }
need() { [[ -n "${2:-}" ]] || die "$1 requires a value"; }
while (( $# )); do
    case "$1" in
        --request-type) need "$1" "${2:-}"; request_type="$2"; shift 2 ;;
        --environment) need "$1" "${2:-}"; environment="$2"; shift 2 ;;
        --owner-project) need "$1" "${2:-}"; owner_project="$2"; shift 2 ;;
        --owner-repo) need "$1" "${2:-}"; owner_repo="$2"; shift 2 ;;
        --operation-sha) need "$1" "${2:-}"; operation_sha="$2"; shift 2 ;;
        --control-plane-sha) need "$1" "${2:-}"; control_plane_sha="$2"; shift 2 ;;
        --workflow-run) need "$1" "${2:-}"; workflow_run="$2"; shift 2 ;;
        --image-tag) need "$1" "${2:-}"; image_tag="$2"; shift 2 ;;
        --web-image) need "$1" "${2:-}"; web_image="$2"; shift 2 ;;
        --api-image) need "$1" "${2:-}"; api_image="$2"; shift 2 ;;
        --worker-image) need "$1" "${2:-}"; worker_image="$2"; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done

python3 - "$request_type" "$environment" "$owner_project" "$owner_repo" "$operation_sha" "$control_plane_sha" "$workflow_run" "$image_tag" "$web_image" "$api_image" "$worker_image" "$REPO_ROOT" <<'PY'
import io
import json
import os
import re
import stat
import sys
import tarfile

request_type, environment, project, repo, sha, control_plane_sha, run_raw, tag, web, api, worker, root = sys.argv[1:]
if request_type not in {"deploy", "rollback"}:
    raise SystemExit("request type must be deploy or rollback")
if environment not in {"staging", "prod"}:
    raise SystemExit("environment must be staging or prod")
if not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", project):
    raise SystemExit("owner.project is invalid")
if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
    raise SystemExit("owner.repo is invalid")
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    raise SystemExit("operation SHA must be 40 lowercase hexadecimal characters")
if not re.fullmatch(r"[0-9a-f]{40}", control_plane_sha):
    raise SystemExit("control-plane SHA must be 40 lowercase hexadecimal characters")
if not re.fullmatch(r"[1-9][0-9]*", run_raw):
    raise SystemExit("workflow run must be a positive integer")
if tag != f"sha-{sha}":
    raise SystemExit("image tag must be canonical sha-<full SHA>")

images = {"web": web, "api": api, "worker": worker}
packages = {"web": "ai-reader-web", "api": "ai-reader-api", "worker": "ai-reader-worker"}
for name,reference in images.items():
    prefix = f"ghcr.io/{repo.lower()}/{packages[name]}@"
    digest = reference[len(prefix):] if reference.startswith(prefix) else ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise SystemExit(f"{name} image must be the expected digest-qualified GHCR repository")

manifest = {
    "contractVersion": "trusted-deploy-bundle/v1",
    "requestType": request_type,
    "environment": environment,
    "owner": {"project": project, "repo": repo},
    "operation": {"fullSha": sha},
    "controlPlane": {"fullSha": control_plane_sha},
    "workflowRun": int(run_raw),
    "imageTag": tag,
    "images": images,
}
payload = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
contract_sources = {
    "verify-shared-edge.sh": os.path.join(root, "infra/deploy/verify-shared-edge.sh"),
    "verify-shared-edge-receipt.mjs": os.path.join(root, "infra/deploy/verify-shared-edge-receipt.mjs"),
    "ensure-shared-edge.sh": os.path.join(root, "infra/deploy/ensure-shared-edge.sh"),
    "rollback-state.sh": os.path.join(root, "infra/deploy/rollback-state.sh"),
}
contract_payloads = {}
for name, path in contract_sources.items():
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise SystemExit(f"{name} must be a non-symbolic regular file")
    with open(path, "rb") as source:
        value = source.read(65537)
    if not value or len(value) > 65536:
        raise SystemExit(f"{name} must be non-empty and at most 64 KiB")
    contract_payloads[name] = value
archive = io.BytesIO()
with tarfile.open(fileobj=archive, mode="w", format=tarfile.USTAR_FORMAT) as output:
    member = tarfile.TarInfo("manifest.json")
    member.size = len(payload)
    member.mode = 0o600
    member.uid = member.gid = member.mtime = 0
    member.uname = member.gname = ""
    output.addfile(member, io.BytesIO(payload))
    for name in sorted(contract_payloads):
        contract_payload = contract_payloads[name]
        member = tarfile.TarInfo(name)
        member.size = len(contract_payload)
        member.mode = 0o555
        member.uid = member.gid = member.mtime = 0
        member.uname = member.gname = ""
        output.addfile(member, io.BytesIO(contract_payload))
sys.stdout.buffer.write(archive.getvalue())
PY

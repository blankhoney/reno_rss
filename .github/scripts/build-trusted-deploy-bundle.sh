#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build the secret-free manifest streamed directly into the locked VPS transaction.
set -euo pipefail

declare request_type='' environment='' owner_project='' owner_repo='' operation_sha='' control_plane_sha=''
declare workflow_run='' image_tag='' web_image='' api_image='' worker_image=''
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

python3 - "$request_type" "$environment" "$owner_project" "$owner_repo" "$operation_sha" "$control_plane_sha" "$workflow_run" "$image_tag" "$web_image" "$api_image" "$worker_image" <<'PY'
import io
import json
import re
import sys
import tarfile

request_type, environment, project, repo, sha, control_plane_sha, run_raw, tag, web, api, worker = sys.argv[1:]
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
archive = io.BytesIO()
with tarfile.open(fileobj=archive, mode="w", format=tarfile.USTAR_FORMAT) as output:
    member = tarfile.TarInfo("manifest.json")
    member.size = len(payload)
    member.mode = 0o600
    member.uid = member.gid = member.mtime = 0
    member.uname = member.gname = ""
    output.addfile(member, io.BytesIO(payload))
sys.stdout.buffer.write(archive.getvalue())
PY

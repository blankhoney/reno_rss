#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Installed as /usr/local/lib/reno-shared-vps/release-lock-v1/trusted-remote-deploy.sh.
# It must be invoked only by the canonical public lock wrapper. stdin is a
# one-line credential frame followed by the secret-free manifest tar.
set -euo pipefail

readonly LOCK_ROOT='/var/lib/reno-shared-vps/release-lock-v1'
readonly LOCK_PATH="$LOCK_ROOT/release.lock"
readonly LOCK_METADATA="$LOCK_ROOT/metadata.json"
readonly MAX_BUNDLE_BYTES=131072
die(){ printf '%s\n' "trusted remote deploy: $*" >&2; exit 64; }
require(){ command -v "$1" >/dev/null 2>&1||die "$1 is required"; }

# Keep this before every redirection, mktemp, Git, or Docker operation.
assert_shared_lock_held(){
 local fd="${SHARED_RELEASE_LOCK_CORE_FD:-}"
 [[ "$(uname -s)" == Linux && "$fd" =~ ^[0-9]+$ && -e "/proc/self/fd/$fd" ]]||die 'canonical shared-lock FD was not inherited'
 [[ "$(readlink -f -- "/proc/self/fd/$fd")" == "$LOCK_PATH" ]]||die 'inherited FD does not reference canonical release.lock'
 [[ -f "$LOCK_METADATA" && ! -L "$LOCK_METADATA" ]]||die 'live shared-lock metadata is missing or unsafe'
 if flock -n "$LOCK_PATH" true 2>/dev/null;then die 'canonical kernel lock is not held by this transaction';fi
}
for command in flock python3 docker git base64 tr sha256sum realpath sed;do require "$command";done
assert_shared_lock_held
: "${VPS_APP_DIR:?VPS_APP_DIR is required}";: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
[[ "$VPS_APP_DIR" == /* && "$VPS_APP_DIR" != *$'\n'* ]]||die 'VPS_APP_DIR must be an absolute single-line path'
[[ "$GHCR_USERNAME" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,38}$ ]]||die 'GHCR_USERNAME is invalid'

transaction_dir='';cleanup(){ local status=$?;trap - EXIT HUP INT TERM;unset token_b64;[[ -z "$transaction_dir" ]]||rm -rf -- "$transaction_dir";exit "$status"; }
trap cleanup EXIT;trap 'exit 129' HUP;trap 'exit 130' INT;trap 'exit 143' TERM

# First remote filesystem mutation: the public wrapper already owns the flock.
umask 077;transaction_dir="$(mktemp -d --tmpdir trusted-rss-deploy.XXXXXXXX)"
bundle_path="$transaction_dir/bundle.tar";manifest_path="$transaction_dir/manifest.json";contract_dir="$transaction_dir/contract";receipt_dir="$transaction_dir/receipts";docker_config_dir="$transaction_dir/docker-config"
mkdir -- "$receipt_dir" "$docker_config_dir";chmod 700 "$docker_config_dir"

IFS= read -r credential_frame||die 'credential frame is missing'
[[ "$credential_frame" =~ ^GHCR_TOKEN_B64\ ([A-Za-z0-9+/]+={0,2})$ ]]||die 'credential frame is invalid'
token_b64="${BASH_REMATCH[1]}";unset credential_frame
python3 -c '
import sys
path,maximum_raw=sys.argv[1:];payload=sys.stdin.buffer.read(int(maximum_raw)+1)
if not payload:raise SystemExit("trusted deploy bundle is empty")
if len(payload)>int(maximum_raw):raise SystemExit("trusted deploy bundle exceeds size limit")
with open(path,"xb") as output:output.write(payload)
' "$bundle_path" "$MAX_BUNDLE_BYTES"
python3 - "$bundle_path" "$manifest_path" "$contract_dir" <<'PY'
import os,sys,tarfile
archive_path,output_path,contract_dir=sys.argv[1:]
expected={"manifest.json","verify-shared-edge.sh","ensure-shared-edge.sh","rollback-state.sh"}
try:
 with tarfile.open(archive_path,mode="r:") as archive:
  members=archive.getmembers()
  if len(members)!=len(expected) or {member.name for member in members}!=expected:raise SystemExit("bundle members do not match the trusted contract")
  payloads={}
  for member in members:
   if not member.isfile() or member.issym() or member.islnk() or not 0<member.size<=65536:raise SystemExit(f"{member.name} must be a bounded regular member")
   source=archive.extractfile(member);payload=source.read(65537) if source else b""
   if len(payload)!=member.size:raise SystemExit(f"{member.name} size mismatch")
   payloads[member.name]=payload
except (tarfile.TarError,OSError) as error:raise SystemExit(f"invalid trusted deploy bundle: {error}") from None
os.mkdir(contract_dir,0o700)
with open(output_path,"xb") as output:output.write(payloads.pop("manifest.json"))
for name,payload in payloads.items():
 path=os.path.join(contract_dir,name)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o500)
 with os.fdopen(fd,"wb") as output:output.write(payload)
PY

mapfile -d '' fields < <(python3 - "$manifest_path" "$LOCK_METADATA" <<'PY'
import json,re,sys
manifest_path,metadata_path=sys.argv[1:]
with open(manifest_path,encoding="utf-8") as source:m=json.load(source)
with open(metadata_path,encoding="utf-8") as source:metadata=json.load(source)
if type(m)is not dict or set(m)!={"contractVersion","requestType","environment","owner","operation","controlPlane","workflowRun","imageTag","images"}:raise SystemExit("manifest schema mismatch")
if m["contractVersion"]!="trusted-deploy-bundle/v1" or m["requestType"] not in {"deploy","rollback"} or m["environment"] not in {"staging","prod"}:raise SystemExit("manifest contract mismatch")
if type(m["owner"])is not dict or set(m["owner"])!={"project","repo"}:raise SystemExit("owner schema mismatch")
project=m["owner"]["project"];repo=m["owner"]["repo"]
if not isinstance(project,str)or not re.fullmatch(r"[a-z][a-z0-9-]{1,63}",project)or not isinstance(repo,str)or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repo):raise SystemExit("owner is invalid")
if type(m["operation"])is not dict or set(m["operation"])!={"fullSha"}:raise SystemExit("operation schema mismatch")
sha=m["operation"]["fullSha"];run=m["workflowRun"]
if not isinstance(sha,str)or not re.fullmatch(r"[0-9a-f]{40}",sha)or type(run)is not int or run<=0 or m["imageTag"]!=f"sha-{sha}":raise SystemExit("operation identity mismatch")
if type(m["controlPlane"])is not dict or set(m["controlPlane"])!={"fullSha"}:raise SystemExit("control-plane schema mismatch")
control_plane_sha=m["controlPlane"]["fullSha"]
if not isinstance(control_plane_sha,str)or not re.fullmatch(r"[0-9a-f]{40}",control_plane_sha):raise SystemExit("control-plane identity mismatch")
if type(m["images"])is not dict or set(m["images"])!={"web","api","worker"}:raise SystemExit("images schema mismatch")
packages={"web":"ai-reader-web","api":"ai-reader-api","worker":"ai-reader-worker"};images=[]
for name in ("web","api","worker"):
 value=m["images"][name];prefix=f"ghcr.io/{repo.lower()}/{packages[name]}@"
 if not isinstance(value,str)or not value.startswith(prefix)or not re.fullmatch(r"sha256:[0-9a-f]{64}",value[len(prefix):]):raise SystemExit(f"images.{name} is invalid")
 images.append(value)
keys={"contractVersion","owner","repo","fullSha","workflowRun","token","acquiredAt","expiresAt","pid","childPid","childPgid","lock","audit"}
if type(metadata)is not dict or set(metadata)!=keys or metadata.get("contractVersion")!=1 or metadata.get("owner")!=project or metadata.get("repo")!=repo or metadata.get("fullSha")!=sha or metadata.get("workflowRun")!=run:raise SystemExit("bundle does not match live lock metadata")
if metadata.get("lock")!={"authority":"live-flock","ttl":"diagnostic-only","path":"/var/lib/reno-shared-vps/release-lock-v1/release.lock"}:raise SystemExit("live lock authority mismatch")
for value in (m["requestType"],m["environment"],project,repo,sha,control_plane_sha,str(run),m["imageTag"],*images):sys.stdout.write(value+"\0")
PY
)
(( ${#fields[@]}==11 ))||die 'manifest did not yield exactly eleven fields'
request_type="${fields[0]}";deploy_env="${fields[1]}";owner_project="${fields[2]}";owner_repo="${fields[3]}";operation_sha="${fields[4]}";control_plane_sha="${fields[5]}";workflow_run="${fields[6]}";image_tag="${fields[7]}";web_image="${fields[8]}";api_image="${fields[9]}";worker_image="${fields[10]}"

export DOCKER_CONFIG="$docker_config_dir"
repo_script(){ printf '%s/%s' "$VPS_APP_DIR" "$1"; }
contract_script(){ printf '%s/%s' "$contract_dir" "$1"; }
run_probe(){
 local phase="$1" runtime="$2" receipt="$receipt_dir/${1}.json" encoded
 shift 2
 bash "$(contract_script verify-shared-edge.sh)" --owner-project "$owner_project" --owner-repo "$owner_repo" --operation-sha "$operation_sha" --workflow-run "$workflow_run" --phase "$phase" --runtime-sha "$runtime" "$@" --receipt "$receipt"||return
 [[ -f "$receipt" && ! -L "$receipt" ]]||die "shared-edge probe did not write a safe $phase receipt"
 encoded="$(base64 < "$receipt"|tr -d '\n')"
 [[ -n "$encoded" ]]||die "shared-edge $phase receipt is empty"
 printf 'TRUSTED_SHARED_EDGE_RECEIPT %s %s\n' "$phase" "$encoded"
}
runtime_containers(){ printf '%s\n' "myrss-${deploy_env}-reader-web-1" "myrss-${deploy_env}-ai-reader-api-1" "myrss-${deploy_env}-ai-reader-worker-1"; }
read_runtime_sha(){ local container revision observed='';while IFS= read -r container;do revision="$(docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$container")"||return;[[ "$revision" =~ ^[0-9a-f]{40}$ ]]||return 1;[[ -z "$observed" || "$observed" == "$revision" ]]||return 1;observed="$revision";done < <(runtime_containers);printf '%s\n' "$observed"; }
capture_runtime_images(){
 local container image image_id repo_digests package expected_repository index=0
 local packages=(ai-reader-web ai-reader-api ai-reader-worker)
 while IFS= read -r container;do
  image="$(docker inspect --format '{{.Config.Image}}' "$container")"||return
  package="${packages[$index]}";expected_repository="ghcr.io/${owner_repo,,}/${package}"
  if [[ "$image" != "$expected_repository"@* || ! "${image#*@}" =~ ^sha256:[0-9a-f]{64}$ ]];then
   image_id="$(docker inspect --format '{{.Image}}' "$container")"||return
   repo_digests="$(docker image inspect --format '{{json .RepoDigests}}' "$image_id")"||return
   image="$(python3 -c '
import json,re,sys
repository=sys.argv[1]
try: values=json.loads(sys.argv[2])
except json.JSONDecodeError:raise SystemExit(1)
matches=sorted(set(value for value in values if isinstance(value,str) and re.fullmatch(re.escape(repository)+r"@sha256:[0-9a-f]{64}",value))) if isinstance(values,list) else []
if len(matches)!=1:raise SystemExit(1)
print(matches[0])
' "$expected_repository" "$repo_digests")"||return
  fi
  printf '%s\n' "$image";index=$((index+1))
 done < <(runtime_containers)
 ((index==3))
}
verify_image(){ local image="$1" sha="$2" revision;docker pull "$image" >/dev/null;revision="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image")";[[ "$revision" == "$sha" ]]||die "OCI revision mismatch for ${image%%@*}"; }
reject_grafts(){ local path;path="$(git --no-replace-objects rev-parse --git-path info/grafts)"||return;[[ ! -s "$path" ]]||die 'legacy Git grafts are forbidden'; }
prepare_control_plane(){ cd "$VPS_APP_DIR";[[ -d .git ]]||die 'VPS_APP_DIR is not a Git repository';[[ -z "$(git --no-replace-objects status --porcelain --untracked-files=all)" ]]||die 'VPS worktree is dirty';export GIT_NO_REPLACE_OBJECTS=1;reject_grafts;[[ "$(git --no-replace-objects rev-parse --is-shallow-repository)" == false ]]||die 'VPS repository is shallow';git --no-replace-objects fetch --no-tags origin 'refs/heads/main:refs/remotes/origin/main';reject_grafts;local main_tip;main_tip="$(git --no-replace-objects rev-parse --verify 'refs/remotes/origin/main^{commit}')";[[ "$main_tip" == "$control_plane_sha" ]]||die 'control-plane SHA is not the fetched trusted main tip';git --no-replace-objects cat-file -e "$operation_sha^{commit}";git --no-replace-objects merge-base --is-ancestor "$operation_sha" "$control_plane_sha"||die 'operation SHA is not on trusted main';git --no-replace-objects checkout --detach "$control_plane_sha"; }
run_production_prebackup(){
 [[ "$deploy_env" == prod ]]||return 0
 local output backup_dir checksum_file backup_root
 if ! output="$(cd "$VPS_APP_DIR" && bash "$(repo_script infra/scripts/backup.sh)" prod 2>&1)";then
  printf '%s\n' "$output" >&2
  die 'production pre-mutation backup failed'
 fi
 printf '%s\n' "$output"
 mapfile -t backup_dirs < <(printf '%s\n' "$output"|sed -n 's/^BACKUP_DIR=//p')
 mapfile -t checksum_files < <(printf '%s\n' "$output"|sed -n 's/^BACKUP_SHA256_FILE=//p')
 (( ${#backup_dirs[@]}==1 && ${#checksum_files[@]}==1 ))||die 'production backup emitted ambiguous evidence markers'
 backup_dir="${backup_dirs[0]}";checksum_file="${checksum_files[0]}"
 [[ "$backup_dir" == /* && "$checksum_file" == /* ]]||die 'production backup evidence paths must be absolute'
 [[ -d "$backup_dir" && ! -L "$backup_dir" && -f "$checksum_file" && ! -L "$checksum_file" ]]||die 'production backup evidence is missing or unsafe'
 backup_root="$(realpath -e -- "$VPS_APP_DIR/backup")"||die 'production backup root is unavailable'
 [[ "$(realpath -e -- "$backup_dir")" == "$backup_root/"* ]]||die 'production backup directory escaped the repository backup root'
 [[ "$(realpath -e -- "$checksum_file")" == "$(realpath -e -- "$backup_dir")/"* ]]||die 'production checksum escaped its backup directory'
 (cd "$backup_dir" && sha256sum -c -- "$checksum_file")||die 'production pre-mutation backup checksum verification failed'
 printf 'trusted production pre-mutation backup verified: %s\n' "$backup_dir"
}
activate_release(){ local sha="$1" web="$2" api="$3" worker="$4";[[ "$(git --no-replace-objects rev-parse HEAD)" == "$control_plane_sha" ]]||return;IMAGE_REGISTRY="ghcr.io/${owner_repo,,}" AI_READER_WEB_IMAGE="$web" AI_READER_API_IMAGE="$api" AI_READER_WORKER_IMAGE="$worker" LOCAL_BUILD=0 bash "$(repo_script infra/scripts/deploy.sh)" "$deploy_env" "sha-${sha}"||return;bash "$(repo_script infra/scripts/smoke-test.sh)" "$deploy_env"||return;[[ "$(read_runtime_sha)" == "$sha" ]]; }
compensation_probe(){ local phase="$1" runtime="$2" rollback_from="$3" target="$4";run_probe "$phase" "$runtime" --rollback-from-sha "$rollback_from" --rollback-target-sha "$target"; }
rollback_web='';rollback_api='';rollback_worker=''
ensure_shared_edge(){ bash "$(contract_script ensure-shared-edge.sh)"; }
activate_rollback(){ local rollback_from="$1" expected_target="$2";[[ "$expected_target" == "$operation_sha" ]]||return 1;activate_release "$rollback_from" "$rollback_web" "$rollback_api" "$rollback_worker"||return;ensure_shared_edge; }

rollback_from="$(read_runtime_sha)"||die 'cannot establish actual pre-activation runtime SHA';[[ "$rollback_from" != "$operation_sha" ]]||die 'operation SHA is already active'
mapfile -t rollback_images < <(capture_runtime_images);(( ${#rollback_images[@]}==3 ))||die 'cannot capture three digest-qualified rollback images';rollback_web="${rollback_images[0]}";rollback_api="${rollback_images[1]}";rollback_worker="${rollback_images[2]}"
run_probe pre-mutation "$rollback_from"
release_and_verify(){
 activate_release "$operation_sha" "$web_image" "$api_image" "$worker_image"||return
 # deploy.sh may recreate Caddy; repair both production memberships again before
 # any successful post-activation/rollback receipt is allowed.
 ensure_shared_edge||return
 if [[ "$request_type" == rollback ]];then
  run_probe post-rollback "$operation_sha" --rollback-from-sha "$rollback_from" --rollback-target-sha "$operation_sha"||return
 else
  run_probe post-activation "$operation_sha"||return
 fi
 if [[ "$deploy_env" == staging && "${RUN_STAGING_RUNTIME_PROOF:-0}" == 1 ]];then
  bash "$(repo_script infra/scripts/staging-runtime-proof.sh)" staging||return
 fi
}
locked_mutation(){
 prepare_control_plane||return
 # Production backup and checksum proof must exist before any edge mutation,
 # registry login, image pull, backend start, migration, or activation.
 run_production_prebackup||return
 ensure_shared_edge||return
 run_probe pre-activation "$rollback_from"||return
 local login_status=0
 printf '%s' "$token_b64"|base64 --decode|docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin >/dev/null||login_status=$?
 unset token_b64
 ((login_status==0))||return "$login_status"
 verify_image "$web_image" "$operation_sha"||return
 verify_image "$api_image" "$operation_sha"||return
 verify_image "$worker_image" "$operation_sha"||return
 release_and_verify
}
set +e;locked_mutation;activation_status=$?;set -e
if ((activation_status!=0));then source "$(contract_script rollback-state.sh)";rollback_state_compensate "$rollback_from" "$operation_sha" read_runtime_sha activate_rollback compensation_probe;exit "$activation_status";fi
printf '%s\n' "trusted remote deploy complete: $request_type $deploy_env @ $operation_sha"

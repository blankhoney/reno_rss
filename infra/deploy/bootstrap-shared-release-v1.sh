#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# One-time, root-operated bootstrap for the canonical shared release lock v1.
set -euo pipefail

readonly LOCK_ROOT='/var/lib/reno-shared-vps/release-lock-v1'
readonly HELPER_ROOT='/usr/local/lib/reno-shared-vps/release-lock-v1'
readonly LOCK_PATH="$LOCK_ROOT/release.lock"
readonly AUDIT_DIR="$LOCK_ROOT/audit"

die() { printf '%s\n' "shared-release-bootstrap: $*" >&2; exit 64; }
[[ ${EUID:-1} -eq 0 ]] || die 'must run as root'
command -v flock >/dev/null || die 'flock is required'
command -v sha256sum >/dev/null || die 'sha256sum is required'
command -v install >/dev/null || die 'install is required'
command -v python3 >/dev/null || die 'python3 is required'
command -v stat >/dev/null || die 'stat is required'
[[ "$(uname -s)" == Linux ]] || die 'shared release bootstrap is supported only on Linux'

PUBLIC_SOURCE=''; CORE_SOURCE=''; TRANSACTION_SOURCE=''
PUBLIC_SUM=''; CORE_SUM=''; TRANSACTION_SUM=''
BUNDLE_STDIN=0; CREATE_GROUP=0; ADD_SUDO_USER=0; USER_ADDED=false; GROUP_CREATED=false
while (($#)); do
  case "$1" in
    --public-source) PUBLIC_SOURCE="${2:-}"; shift 2 ;;
    --core-source) CORE_SOURCE="${2:-}"; shift 2 ;;
    --transaction-source) TRANSACTION_SOURCE="${2:-}"; shift 2 ;;
    --public-sha256) PUBLIC_SUM="${2:-}"; shift 2 ;;
    --core-sha256) CORE_SUM="${2:-}"; shift 2 ;;
    --transaction-sha256) TRANSACTION_SUM="${2:-}"; shift 2 ;;
    --bundle-stdin) BUNDLE_STDIN=1; shift ;;
    --create-group) CREATE_GROUP=1; shift ;;
    --add-sudo-user) ADD_SUDO_USER=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done
[[ -n "$PUBLIC_SUM" && -n "$CORE_SUM" && -n "$TRANSACTION_SUM" ]] || die 'all three expected SHA-256 values are required'
if (( BUNDLE_STDIN == 0 )); then [[ -n "$PUBLIC_SOURCE" && -n "$CORE_SOURCE" && -n "$TRANSACTION_SOURCE" ]] || die 'all three source files are required without --bundle-stdin'; fi
if (( BUNDLE_STDIN == 1 )); then [[ -z "$PUBLIC_SOURCE$CORE_SOURCE$TRANSACTION_SOURCE" ]] || die '--bundle-stdin cannot be combined with source paths'; fi
[[ "$PUBLIC_SUM" =~ ^[0-9a-f]{64}$ && "$CORE_SUM" =~ ^[0-9a-f]{64}$ && "$TRANSACTION_SUM" =~ ^[0-9a-f]{64}$ ]] || die 'expected SHA-256 values must be lowercase 64-hex strings'

assert_source() {
  local path="$1"
  [[ -f "$path" && ! -L "$path" ]] || die "source must be a non-symbolic regular file"
  sha256sum -- "$path" | awk '{print $1}'
}
if (( BUNDLE_STDIN == 0 )); then
 [[ "$(assert_source "$PUBLIC_SOURCE")" == "$PUBLIC_SUM" ]] || die 'public source checksum mismatch'
 [[ "$(assert_source "$CORE_SOURCE")" == "$CORE_SUM" ]] || die 'core source checksum mismatch'
 [[ "$(assert_source "$TRANSACTION_SOURCE")" == "$TRANSACTION_SUM" ]] || die 'transaction source checksum mismatch'
fi

# Serialize first-use without trusting a pre-created mutex.  O_EXCL prevents
# the creation race; an existing mutex must exactly match this root-only file.
python3 - /run/lock/reno-shared-release-bootstrap-v1.lock <<'PY'
import errno,os,stat,sys
path=sys.argv[1]
try:
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600); os.close(fd)
except FileExistsError: pass
st=os.lstat(path)
if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_gid!=0 or stat.S_IMODE(st.st_mode)!=0o600 or st.st_size!=0:
 raise SystemExit("unsafe bootstrap mutex")
PY
exec {INIT_FD}>/run/lock/reno-shared-release-bootstrap-v1.lock
flock "$INIT_FD"
if ! getent group reno-deploy >/dev/null; then
  (( CREATE_GROUP == 1 )) || die 'required group reno-deploy does not exist; use --create-group in the controlled bootstrap'
  groupadd -- reno-deploy
  GROUP_CREATED=true
fi
if (( ADD_SUDO_USER == 1 )); then
  [[ "${SUDO_USER:-}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die '--add-sudo-user requires a bounded SUDO_USER'
  id -- "$SUDO_USER" >/dev/null || die 'SUDO_USER does not identify a local account'
  if ! id -nG -- "$SUDO_USER" | tr ' ' '\n' | grep -qx reno-deploy; then usermod -aG reno-deploy -- "$SUDO_USER"; USER_ADDED=true; fi
fi
export BOOTSTRAP_USER_ADDED="$USER_ADDED"
export BOOTSTRAP_GROUP_CREATED="$GROUP_CREATED"

assert_path() {
  local path="$1" type="$2" mode="$3" actual
  [[ ! -L "$path" && -e "$path" ]] || die "path is missing or symbolic-linked: $path"
  actual="$(stat -Lc '%F:%U:%G:%a' -- "$path")" || die "cannot inspect $path"
  [[ "$actual" == "$type:root:reno-deploy:$mode" ]] || die "existing path has unsafe owner, group, or mode: $path"
}
create_lock_tree_once() {
  if [[ ! -e "$LOCK_ROOT" && ! -L "$LOCK_ROOT" ]]; then install -d -o root -g reno-deploy -m 0770 "$LOCK_ROOT"; fi
  assert_path "$LOCK_ROOT" directory 770
  if [[ ! -e "$AUDIT_DIR" && ! -L "$AUDIT_DIR" ]]; then install -d -o root -g reno-deploy -m 0770 "$AUDIT_DIR"; fi
  assert_path "$AUDIT_DIR" directory 770
  if [[ ! -e "$LOCK_PATH" && ! -L "$LOCK_PATH" ]]; then install -o root -g reno-deploy -m 0660 /dev/null "$LOCK_PATH"; fi
  assert_path "$LOCK_PATH" 'regular empty file' 660
}

create_lock_tree_once
filesystem_type="$(stat -fLc '%T' -- "$LOCK_ROOT")" || die 'cannot identify lock filesystem'
case "$filesystem_type" in ext2|ext3|ext4|xfs|btrfs|tmpfs|overlayfs) ;; *) die "lock root must be on a local Linux flock filesystem, got $filesystem_type" ;; esac
root_device="$(stat -Lc '%d' -- "$LOCK_ROOT")"
lock_device="$(stat -Lc '%d' -- "$LOCK_PATH")"
audit_device="$(stat -Lc '%d' -- "$AUDIT_DIR")"
[[ "$root_device" == "$lock_device" && "$root_device" == "$audit_device" ]] || die 'root, lock, and audit must share one local filesystem'
# Do not replace this file: this exact inode is the shared kernel-lock anchor.
exec {LOCK_FD}>"$LOCK_PATH"
flock -n "$LOCK_FD" || die 'another bootstrap or release owns the canonical lock'

if (( BUNDLE_STDIN == 1 )); then
  BUNDLE_DIR="$LOCK_ROOT/.bootstrap-bundle.${BASHPID}.${RANDOM}"
  cleanup_bundle() { [[ -z "${BUNDLE_DIR:-}" ]] || rm -r -f -- "$BUNDLE_DIR"; }
  trap cleanup_bundle EXIT
  trap 'cleanup_bundle; exit 128' INT TERM HUP
  install -d -o root -g root -m 0700 "$BUNDLE_DIR"
  # Read no more than 4 MiB from stdin, then require exactly the three regular
  # members below.  Nothing is extracted outside this flock-protected root.
  python3 - "$BUNDLE_DIR" 3<&0 <<'PY'
import io,os,sys,tarfile
directory=sys.argv[1]
payload=os.fdopen(3,"rb").read(4*1024*1024+1)
if len(payload)>4*1024*1024: raise SystemExit("bundle exceeds 4 MiB")
try: archive=tarfile.open(fileobj=io.BytesIO(payload),mode="r:*")
except tarfile.TarError as e: raise SystemExit("invalid bundle") from e
expected={"with-shared-release-lock.sh","internal/shared-release-lock-core.sh","trusted-remote-deploy.sh"}
members=archive.getmembers()
if {m.name for m in members}!=expected or len(members)!=3: raise SystemExit("bundle members are not exact")
for member in members:
 if not member.isfile() or member.issym() or member.islnk() or member.size>1024*1024: raise SystemExit("bundle member is unsafe")
 if member.name.startswith("/") or ".." in member.name.split("/"): raise SystemExit("bundle traversal")
 target=os.path.join(directory,member.name)
 os.makedirs(os.path.dirname(target),exist_ok=True)
 with archive.extractfile(member) as source, open(target,"xb") as output: output.write(source.read())
PY
  PUBLIC_SOURCE="$BUNDLE_DIR/with-shared-release-lock.sh"
  CORE_SOURCE="$BUNDLE_DIR/internal/shared-release-lock-core.sh"
  TRANSACTION_SOURCE="$BUNDLE_DIR/trusted-remote-deploy.sh"
  [[ "$(assert_source "$PUBLIC_SOURCE")" == "$PUBLIC_SUM" ]] || die 'public bundle checksum mismatch'
  [[ "$(assert_source "$CORE_SOURCE")" == "$CORE_SUM" ]] || die 'core bundle checksum mismatch'
  [[ "$(assert_source "$TRANSACTION_SOURCE")" == "$TRANSACTION_SUM" ]] || die 'transaction bundle checksum mismatch'
fi

audit() {
  local event="$1" path="$AUDIT_DIR/$(date -u +'%Y%m%dT%H%M%SZ')-${BASHPID}-${RANDOM}-bootstrap.json"
  local public="$2" core="$3" transaction="$4"
  umask 077
  python3 - "$path" "$event" "$public" "$core" "$transaction" "$LOCK_PATH" <<'PY'
import json,os,sys
from datetime import datetime,timezone
path,event,public,core,transaction,lock_path=sys.argv[1:]
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,"w",encoding="utf-8") as f:
 f.write(json.dumps({"contractVersion":1,"event":event,"timestamp":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"lockPath":lock_path,"groupCreated":os.environ.get("BOOTSTRAP_GROUP_CREATED")=="true","sudoUserAdded":os.environ.get("BOOTSTRAP_USER_ADDED")=="true","sources":{"publicSha256":public,"coreSha256":core,"transactionSha256":transaction}},sort_keys=True,separators=(",",":"))+"\n")
PY
}

install_helper() {
  local source="$1" name="$2" expected_sum="$3" parent='' staged=''
  parent="$HELPER_ROOT/$(dirname -- "$name")"
  staged="$parent/.${name##*/}.${BASHPID}.tmp"
  [[ "$(assert_source "$source")" == "$expected_sum" ]] || die "source checksum changed before install: $name"
  [[ ! -L "$HELPER_ROOT" ]] || die 'helper directory must not be symbolic-linked'
  if [[ ! -e "$HELPER_ROOT" ]]; then install -d -o root -g root -m 0755 "$HELPER_ROOT"; fi
  [[ "$(stat -Lc '%F:%U:%G:%a' -- "$HELPER_ROOT")" == 'directory:root:root:755' ]] || die 'helper directory has unsafe ownership or mode'
  [[ ! -L "$parent" ]] || die 'helper subdirectory must not be symbolic-linked'
  if [[ ! -e "$parent" ]]; then install -d -o root -g root -m 0755 "$parent"; fi
  [[ ! -L "$parent" && "$(stat -Lc '%F:%U:%G:%a' -- "$parent")" == 'directory:root:root:755' ]] || die 'helper subdirectory has unsafe ownership or mode'
  install -o root -g root -m 0555 -- "$source" "$staged"
  [[ "$(assert_source "$source")" == "$expected_sum" ]] || die "source checksum changed before rename: $name"
  # rename is atomic within the pre-existing helper directory.
  mv -f -- "$staged" "$HELPER_ROOT/$name"
  [[ "$(stat -Lc '%F:%U:%G:%a' -- "$HELPER_ROOT/$name")" == 'regular file:root:root:555' ]] || die 'installed helper verification failed'
}

install_helper "$PUBLIC_SOURCE" with-shared-release-lock.sh "$PUBLIC_SUM"
install_helper "$CORE_SOURCE" internal/shared-release-lock-core.sh "$CORE_SUM"
install_helper "$TRANSACTION_SOURCE" trusted-remote-deploy.sh "$TRANSACTION_SUM"
audit bootstrap-or-upgrade "$PUBLIC_SUM" "$CORE_SUM" "$TRANSACTION_SUM"

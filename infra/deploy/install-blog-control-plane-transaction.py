#!/usr/bin/env python3
"""Install the audited Blog control plane while the canonical flock is held."""
from __future__ import annotations

import argparse
import grp
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

LOCK_ROOT = pathlib.Path('/var/lib/reno-shared-vps/release-lock-v1')
LOCK_PATH = LOCK_ROOT / 'release.lock'
METADATA_PATH = LOCK_ROOT / 'metadata.json'
AUDIT_DIR = LOCK_ROOT / 'audit'
HELPER_ROOT = pathlib.Path('/usr/local/lib/reno-shared-vps/release-lock-v1')
APP_ROOT = pathlib.Path('/srv/brianstorm')
TARGETS = {
    'trusted-blog-remote-transaction.sh': ('45c326fdd266311df5ac1114c4c47207429efc6b47bd795db4d6f06b0f602892', HELPER_ROOT / 'trusted-blog-remote-transaction.sh'),
    'verify-shared-edge.sh': ('8ad9f32344ab8007c503850a7c3b0f680ccf13cd3b06d95fa673221ac5d73766', HELPER_ROOT / 'verify-shared-edge.sh'),
    'verify-shared-edge-receipt.mjs': ('6102cf625a0b604c0d1ab52226139727fa287811928e4b33dc53f527dd75262c', HELPER_ROOT / 'verify-shared-edge-receipt.mjs'),
}
WRAPPER_SHA = '2cf87eb5d54e626fd96bef70ea7b8543ef721a12bb610b31dd2578fb80c296a5'
CORE_SHA = 'd54485e473c7729e74628105c0f0ca6f75bcc63e65d4b71c2f14f1e2f3b51429'
SHA = re.compile(r'^[a-f0-9]{40}$')
DIGEST = re.compile(r'^sha256:[a-f0-9]{64}$')


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def exact(value: object, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise RuntimeError(f'{label}_schema')
    return value


def safe_regular(path: pathlib.Path, owner: int = 0, group: int = 0, mode: int = 0o555) -> None:
    value = path.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != owner or value.st_gid != group
            or stat.S_IMODE(value.st_mode) != mode):
        raise RuntimeError(f'unsafe_{path.name}')


def write_exclusive(path: pathlib.Path, payload: bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def fsync_dir(path: pathlib.Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(allow_abbrev=False)
    for name in ('repo', 'control-plane-sha', 'operation-sha', 'rss-source-sha',
                 'rss-installer-sha', 'artifact-digest', 'web-image-digest',
                 'companion-image-digest', 'installer-transaction-sha256'):
        value.add_argument(f'--{name}', required=True)
    for name in ('bundle-fd', 'installer-run', 'installer-attempt', 'control-ci-run',
                 'control-ci-attempt', 'producer-run', 'producer-attempt', 'artifact-id'):
        value.add_argument(f'--{name}', required=True, type=int)
    return value


def validate_args(args: argparse.Namespace) -> None:
    if os.geteuid() != 0 or os.uname().sysname != 'Linux':
        raise RuntimeError('root_linux_required')
    if args.bundle_fd != 8 or os.environ.get('RENO_SHARED_RELEASE_BUNDLE_FD') != '8':
        raise RuntimeError('bundle_fd')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repo):
        raise RuntimeError('repo')
    for value in (args.control_plane_sha, args.operation_sha, args.rss_source_sha, args.rss_installer_sha):
        if not SHA.fullmatch(value):
            raise RuntimeError('sha')
    for value in (args.bundle_fd, args.installer_run, args.installer_attempt, args.control_ci_run,
                  args.control_ci_attempt, args.producer_run, args.producer_attempt, args.artifact_id):
        if value <= 0:
            raise RuntimeError('positive_integer')
    for value in (args.artifact_digest, args.web_image_digest, args.companion_image_digest):
        if not DIGEST.fullmatch(value):
            raise RuntimeError('digest')
    if not re.fullmatch(r'[a-f0-9]{64}', args.installer_transaction_sha256):
        raise RuntimeError('installer_transaction_digest')
    if args.repo != 'blankhoney/my_blog' or args.rss_source_sha != '2b29cfafaafa0795401c7b226a159572f9af6729':
        raise RuntimeError('frozen_identity')


def validate_lock(args: argparse.Namespace) -> tuple[dict, str, str]:
    fd_raw = os.environ.get('SHARED_RELEASE_LOCK_CORE_FD', '')
    if not fd_raw.isdigit() or os.environ.get('SHARED_RELEASE_LOCK_ROOT') != str(LOCK_ROOT):
        raise RuntimeError('lock_environment')
    fd = int(fd_raw)
    fd_target = pathlib.Path(f'/proc/self/fd/{fd}').resolve(strict=True)
    if fd_target != LOCK_PATH or os.stat(fd).st_dev != LOCK_PATH.stat().st_dev or os.stat(fd).st_ino != LOCK_PATH.stat().st_ino:
        raise RuntimeError('lock_inode')
    metadata = exact(json.loads(METADATA_PATH.read_text()), {
        'contractVersion', 'owner', 'repo', 'fullSha', 'workflowRun', 'token',
        'acquiredAt', 'expiresAt', 'pid', 'childPid', 'childPgid', 'lock', 'audit'}, 'lock')
    if (metadata['contractVersion'] != 1 or metadata['owner'] != 'blog' or metadata['repo'] != args.repo
            or metadata['fullSha'] != args.operation_sha or metadata['workflowRun'] != args.installer_run
            or metadata['childPid'] != os.getpid() or metadata['childPgid'] != os.getpid()
            or metadata['lock'] != {'authority': 'live-flock', 'ttl': 'diagnostic-only', 'path': str(LOCK_PATH)}
            or metadata['audit'] != {'state': 'held', 'lastEvent': 'acquired'}
            or not re.fullmatch(r'[a-f0-9]{64}', metadata.get('token', ''))):
        raise RuntimeError('lock_metadata')
    token_digest = sha256_bytes(metadata['token'].encode())
    return metadata, token_digest, f'{LOCK_PATH.stat().st_dev}:{LOCK_PATH.stat().st_ino}'


def validate_platform() -> dict:
    deploy_group = grp.getgrnam('reno-deploy').gr_gid
    expected = [(LOCK_ROOT, stat.S_IFDIR, deploy_group, 0o770),
                (LOCK_PATH, stat.S_IFREG, deploy_group, 0o660),
                (AUDIT_DIR, stat.S_IFDIR, deploy_group, 0o770),
                (HELPER_ROOT, stat.S_IFDIR, 0, 0o755)]
    for path, kind, group, mode in expected:
        value = path.lstat()
        if (stat.S_IFMT(value.st_mode) != kind or value.st_uid != 0 or value.st_gid != group
                or stat.S_IMODE(value.st_mode) != mode):
            raise RuntimeError(f'unsafe_{path.name}')
    wrapper = HELPER_ROOT / 'with-shared-release-lock.sh'
    core = HELPER_ROOT / 'internal/shared-release-lock-core.sh'
    safe_regular(wrapper)
    safe_regular(core)
    if sha256_file(wrapper) != WRAPPER_SHA or sha256_file(core) != CORE_SHA:
        raise RuntimeError('canonical_helper_digest')
    lock_stat = LOCK_PATH.stat()
    return {'root': str(LOCK_ROOT), 'lockPath': str(LOCK_PATH),
            'lockDeviceInode': f'{lock_stat.st_dev}:{lock_stat.st_ino}',
            'owner': 'root', 'group': 'reno-deploy', 'rootMode': '0770',
            'lockMode': '0660', 'auditMode': '0770'}


def current_runtime(args: argparse.Namespace) -> str:
    current = APP_ROOT / 'current'
    if not current.is_symlink():
        raise RuntimeError('current_not_symlink')
    resolved = current.resolve(strict=True)
    releases = (APP_ROOT / 'releases').resolve(strict=True)
    if releases not in resolved.parents:
        raise RuntimeError('current_escape')
    provenance = resolved / 'release-provenance.json'
    provenance_stat = provenance.lstat()
    if not stat.S_ISREG(provenance_stat.st_mode):
        raise RuntimeError('runtime_provenance_unsafe')
    value = exact(json.loads(provenance.read_text()), {'candidateSha', 'companionImage',
        'imageArchiveSha256', 'repository', 'schemaVersion', 'sourceArchiveSha256',
        'webImage', 'workflowRunId'}, 'runtime')
    if (value['schemaVersion'] != 1 or value['repository'] != args.repo
            or value['candidateSha'] != args.operation_sha
            or value['workflowRunId'] != args.producer_run
            or not re.fullmatch(r'[a-f0-9]{64}', value['sourceArchiveSha256'])
            or not re.fullmatch(r'[a-f0-9]{64}', value['imageArchiveSha256'])
            or value['webImage'] != {'id': args.web_image_digest,
                'reference': f'brianstorm-web:{args.operation_sha}'}
            or value['companionImage'] != {'id': args.companion_image_digest,
                'reference': f'brianstorm-vps-companion:production-{args.operation_sha}'}):
        raise RuntimeError('runtime_identity')
    return value['candidateSha']


def extract_bundle(fd: int, directory: pathlib.Path) -> dict[str, pathlib.Path]:
    payload = os.fdopen(os.dup(fd), 'rb').read(2 * 1024 * 1024 + 1)
    if not payload or len(payload) > 2 * 1024 * 1024:
        raise RuntimeError('bundle_size')
    try:
        archive = tarfile.open(fileobj=io.BytesIO(payload), mode='r:')
    except tarfile.TarError as error:
        raise RuntimeError('bundle_tar') from error
    members = archive.getmembers()
    if len(members) != len(TARGETS) or {item.name for item in members} != set(TARGETS):
        raise RuntimeError('bundle_members')
    result = {}
    for item in members:
        if not item.isfile() or item.issym() or item.islnk() or pathlib.PurePosixPath(item.name).name != item.name:
            raise RuntimeError('bundle_member_type')
        source = archive.extractfile(item)
        if source is None:
            raise RuntimeError('bundle_member_read')
        target = directory / item.name
        write_exclusive(target, source.read(), 0o600)
        expected, _ = TARGETS[item.name]
        if sha256_file(target) != expected:
            raise RuntimeError('bundle_digest')
        result[item.name] = target
    return result


def run_probe(probe: pathlib.Path, verifier: pathlib.Path, receipt: pathlib.Path,
              args: argparse.Namespace, runtime: str, phase: str) -> str:
    subprocess.run(['bash', str(probe), '--owner-project', 'blog', '--owner-repo', args.repo,
        '--operation-sha', args.operation_sha, '--runtime-sha', runtime,
        '--workflow-run', str(args.installer_run), '--phase', phase, '--receipt', str(receipt)],
        check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['node', str(verifier), str(receipt), 'success', 'blog', args.repo,
        args.operation_sha, runtime, str(args.installer_run), phase],
        check=True, stdout=subprocess.DEVNULL)
    return sha256_file(receipt)


def atomic_install(files: dict[str, pathlib.Path]) -> tuple[dict[pathlib.Path, bytes | None], dict[str, str]]:
    previous: dict[pathlib.Path, bytes | None] = {}
    staged: dict[pathlib.Path, pathlib.Path] = {}
    replaced: list[pathlib.Path] = []
    installed = {}
    try:
        for name, source in files.items():
            digest, target = TARGETS[name]
            if target.exists() or target.is_symlink():
                safe_regular(target)
                previous[target] = target.read_bytes()
            else:
                previous[target] = None
            stage = HELPER_ROOT / f'.{target.name}.{os.getpid()}.tmp'
            write_exclusive(stage, source.read_bytes(), 0o555)
            os.chown(stage, 0, 0)
            safe_regular(stage)
            if sha256_file(stage) != digest:
                raise RuntimeError('staged_digest')
            staged[target] = stage
        for target, stage in staged.items():
            os.replace(stage, target)
            replaced.append(target)
        fsync_dir(HELPER_ROOT)
        for name, (_, target) in TARGETS.items():
            safe_regular(target)
            installed[name] = sha256_file(target)
    except Exception:
        restore({target: previous[target] for target in replaced})
        raise
    finally:
        for stage in staged.values():
            stage.unlink(missing_ok=True)
    return previous, installed


def restore(previous: dict[pathlib.Path, bytes | None]) -> None:
    for target, payload in previous.items():
        if payload is None:
            target.unlink(missing_ok=True)
        else:
            stage = HELPER_ROOT / f'.{target.name}.{os.getpid()}.restore'
            if stage.exists():
                stage.unlink()
            write_exclusive(stage, payload, 0o555)
            os.chown(stage, 0, 0)
            os.replace(stage, target)
    fsync_dir(HELPER_ROOT)


def audit_write(name: str, value: dict) -> pathlib.Path:
    path = AUDIT_DIR / name
    payload = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    write_exclusive(path, payload)
    fsync_dir(AUDIT_DIR)
    return path


def persist_probe(name: str, source: pathlib.Path) -> pathlib.Path:
    path = AUDIT_DIR / name
    write_exclusive(path, source.read_bytes())
    fsync_dir(AUDIT_DIR)
    return path


def main() -> int:
    args = parser().parse_args()
    validate_args(args)
    metadata, token_digest, inode = validate_lock(args)
    canonical = validate_platform()
    if canonical['lockDeviceInode'] != inode:
        raise RuntimeError('lock_inode_drift')

    work = pathlib.Path(tempfile.mkdtemp(prefix='.blog-control-plane-v2.', dir=LOCK_ROOT))
    previous = None
    stage = 'bundle'
    try:
        files = extract_bundle(args.bundle_fd, work)
        runtime = current_runtime(args)
        stage = 'before_probe'
        before = work / 'before.json'
        before_digest = run_probe(files['verify-shared-edge.sh'], files['verify-shared-edge-receipt.mjs'],
                                  before, args, runtime, 'pre-mutation')
        stage = 'install'
        previous, installed = atomic_install(files)
        stage = 'after_probe'
        after = work / 'after.json'
        after_digest = run_probe(TARGETS['verify-shared-edge.sh'][1], TARGETS['verify-shared-edge-receipt.mjs'][1],
                                 after, args, runtime, 'pre-activation')
        timestamp = utc_now()
        suffix = f'{args.installer_run}-{args.installer_attempt}'
        before_path = persist_probe(f'blog-control-plane-v2-{suffix}-before.json', before)
        after_path = persist_probe(f'blog-control-plane-v2-{suffix}-after.json', after)
        receipt = {
            'contractVersion': 2, 'event': 'blog-control-plane-installed',
            'owner': {'project': 'rss', 'repo': 'blankhoney/reno_rss'},
            'controlPlane': {'repo': args.repo, 'fullSha': args.control_plane_sha,
                'workflowRun': args.control_ci_run, 'workflowRunAttempt': args.control_ci_attempt},
            'operation': {'repo': args.repo, 'fullSha': args.operation_sha,
                'workflowRun': args.producer_run, 'workflowRunAttempt': args.producer_attempt,
                'artifactId': args.artifact_id, 'artifactDigest': args.artifact_digest,
                'webImageDigest': args.web_image_digest, 'companionImageDigest': args.companion_image_digest},
            'installer': {'repo': 'blankhoney/reno_rss', 'fullSha': args.rss_installer_sha,
                'workflowRun': args.installer_run, 'workflowRunAttempt': args.installer_attempt},
            'source': {'rssSourceSha': args.rss_source_sha, 'wrapperSha256': WRAPPER_SHA,
                'installerTransactionSha256': args.installer_transaction_sha256,
                'coreSha256': CORE_SHA, 'transactionSha256': TARGETS['trusted-blog-remote-transaction.sh'][0],
                'probeSha256': TARGETS['verify-shared-edge.sh'][0],
                'probeVerifierSha256': TARGETS['verify-shared-edge-receipt.mjs'][0]},
            'installed': {'wrapperSha256': WRAPPER_SHA, 'coreSha256': CORE_SHA,
                'transactionSha256': installed['trusted-blog-remote-transaction.sh'],
                'probeSha256': installed['verify-shared-edge.sh'],
                'probeVerifierSha256': installed['verify-shared-edge-receipt.mjs']},
            'canonical': canonical,
            'lock': {'authority': 'live-flock', 'tokenSha256': token_digest,
                'audit': metadata['audit'], 'acquiredAt': metadata['acquiredAt']},
            'probes': {'before': {'phase': 'pre-mutation', 'receiptPath': str(before_path), 'sha256': before_digest},
                'after': {'phase': 'pre-activation', 'receiptPath': str(after_path), 'sha256': after_digest}},
            'timestamp': timestamp,
        }
        audit_write(f'blog-control-plane-v2-{suffix}-installed.json', receipt)
        previous = None
        print(json.dumps(receipt, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception as error:
        if previous is not None:
            restore(previous)
        failure = {'contractVersion': 2, 'event': 'blog-control-plane-install-failed',
            'owner': {'project': 'rss', 'repo': 'blankhoney/reno_rss'},
            'controlPlaneSha': args.control_plane_sha, 'operationSha': args.operation_sha,
            'installerRun': args.installer_run, 'installerAttempt': args.installer_attempt,
            'stage': stage, 'error': type(error).__name__, 'timestamp': utc_now()}
        audit_write(f'blog-control-plane-v2-{args.installer_run}-{args.installer_attempt}-failed.json', failure)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'Blog control-plane installer failed closed: {type(error).__name__}', file=sys.stderr)
        raise SystemExit(64)

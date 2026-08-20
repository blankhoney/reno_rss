#!/usr/bin/env python3
"""Install the audited Blog control plane while the canonical flock is held."""
from __future__ import annotations

import argparse
import errno
import grp
import hashlib
import io
import json
import os
import pathlib
import pwd
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
WORK_ROOT = pathlib.Path('/run')
APP_ROOT = pathlib.Path('/srv/brianstorm')
TARGETS = {
    'trusted-blog-remote-transaction.sh': ('45c326fdd266311df5ac1114c4c47207429efc6b47bd795db4d6f06b0f602892', HELPER_ROOT / 'trusted-blog-remote-transaction.sh'),
    'verify-shared-edge.sh': ('8ad9f32344ab8007c503850a7c3b0f680ccf13cd3b06d95fa673221ac5d73766', HELPER_ROOT / 'verify-shared-edge.sh'),
    'verify-shared-edge-receipt.mjs': ('6102cf625a0b604c0d1ab52226139727fa287811928e4b33dc53f527dd75262c', HELPER_ROOT / 'verify-shared-edge-receipt.mjs'),
}
WRAPPER_SHA = '2cf87eb5d54e626fd96bef70ea7b8543ef721a12bb610b31dd2578fb80c296a5'
CORE_SHA = 'd54485e473c7729e74628105c0f0ca6f75bcc63e65d4b71c2f14f1e2f3b51429'
LEGACY_RUNTIME_SHA = '1667b3c891958c65426d9f3ed7dd0426f012cefc'
LEGACY_RELEASE_ID = '20260719-201357-1667b3c'
PROBE_ACCOUNT = 'deploy'
SHA = re.compile(r'^[a-f0-9]{40}$')
DIGEST = re.compile(r'^sha256:[a-f0-9]{64}$')
NODE_LAYOUTS = ('system_usr_local_bin', 'system_usr_bin', 'nvm', 'asdf', 'mise', 'fnm')


class NodeResolutionError(RuntimeError):
    def __init__(self, message: str, diagnostics: dict[str, dict[str, int]]):
        super().__init__(message)
        self.diagnostics = diagnostics


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


def chown_as_root(path: pathlib.Path, owner: int, group: int) -> None:
    if os.geteuid() == 0:
        os.chown(path, owner, group)


def file_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def freeze_probe_node(source_fd: int, work: pathlib.Path) -> tuple[pathlib.Path, str]:
    target = work / 'node'
    target_fd = -1
    try:
        before = os.fstat(source_fd)
        if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) & 0o111 == 0
                or before.st_size <= 0 or before.st_size > 256 * 1024 * 1024):
            raise RuntimeError('probe_node_permissions')
        target_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o500)
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            view = memoryview(block)
            while view:
                view = view[os.write(target_fd, view):]
        os.fsync(target_fd)
        os.fchmod(target_fd, 0o555)
        if os.geteuid() == 0:
            os.fchown(target_fd, 0, 0)
        after = os.fstat(source_fd)
        if file_identity(before) != file_identity(after):
            raise RuntimeError('probe_node_changed')
    finally:
        if target_fd >= 0:
            os.close(target_fd)
    return target, sha256_file(target)


def freeze_probe_receipt(source: pathlib.Path, target: pathlib.Path,
                         args: argparse.Namespace) -> None:
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != args.probe_uid
                or before.st_gid != args.probe_gid or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_size <= 0 or before.st_size > 1024 * 1024):
            raise RuntimeError('probe_receipt_permissions')
        payload = b''
        while True:
            block = os.read(fd, 64 * 1024)
            if not block:
                break
            payload += block
        after = os.fstat(fd)
        current = source.lstat()
        if file_identity(before) != file_identity(after) or file_identity(after) != file_identity(current):
            raise RuntimeError('probe_receipt_changed')
        write_exclusive(target, payload, 0o440)
        chown_as_root(target, 0, args.probe_gid)
        os.chmod(target, 0o440)
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
    for name in ('INSTALLER_PROBE_UID', 'INSTALLER_PROBE_GID', 'INSTALLER_PROBE_USER'):
        if name in os.environ:
            raise RuntimeError('probe_identity_override')
    account = pwd.getpwnam(PROBE_ACCOUNT)
    if account.pw_uid <= 0 or account.pw_gid < 0:
        raise RuntimeError('probe_identity')
    args.probe_uid = account.pw_uid
    args.probe_gid = account.pw_gid


def validate_directory_fd(fd: int, owner: int) -> None:
    value = os.fstat(fd)
    if (not stat.S_ISDIR(value.st_mode) or value.st_uid != owner
            or stat.S_IMODE(value.st_mode) & 0o022):
        raise RuntimeError('probe_node_directory')


def open_directory_at(parent_fd: int, name: str, owner: int) -> int:
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        validate_directory_fd(fd, owner)
        return fd
    except Exception:
        os.close(fd)
        raise


def open_directory_chain(parts: tuple[str, ...], final_owner: int) -> int:
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    validate_directory_fd(fd, 0)
    current_owner = 0
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            value = os.fstat(child)
            if current_owner == 0 and value.st_uid == final_owner:
                current_owner = final_owner
            if (not stat.S_ISDIR(value.st_mode) or value.st_uid != current_owner
                    or stat.S_IMODE(value.st_mode) & 0o022):
                os.close(child)
                raise RuntimeError('probe_node_directory')
            os.close(fd)
            fd = child
        if current_owner != final_owner:
            raise RuntimeError('probe_node_directory')
        return fd
    except Exception:
        os.close(fd)
        raise


def open_node_at(parent_fd: int, owner: int) -> int:
    fd = os.open('node', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        value = os.fstat(fd)
        if (not stat.S_ISREG(value.st_mode) or value.st_uid != owner
                or stat.S_IMODE(value.st_mode) & 0o111 == 0
                or stat.S_IMODE(value.st_mode) & 0o022
                or value.st_size <= 0 or value.st_size > 256 * 1024 * 1024):
            raise RuntimeError('probe_node_permissions')
        return fd
    except Exception:
        os.close(fd)
        raise


def probe_node_version(fd: int, args: argparse.Namespace) -> tuple[int, int, int]:
    account = pwd.getpwuid(args.probe_uid)
    environment = {'HOME': account.pw_dir, 'USER': account.pw_name, 'LOGNAME': account.pw_name,
        'LANG': 'C.UTF-8', 'PATH': '/usr/local/bin:/usr/bin:/bin'}
    credentials = {}
    if os.geteuid() == 0:
        credentials = {'user': args.probe_uid, 'group': args.probe_gid,
            'extra_groups': os.getgrouplist(account.pw_name, args.probe_gid)}
    result = subprocess.run([f'/proc/self/fd/{fd}', '--version'], check=False, text=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=5, env=environment, pass_fds=(fd,), **credentials)
    match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)\s*', result.stdout)
    if result.returncode != 0 or match is None:
        raise RuntimeError('probe_node_version')
    version = tuple(map(int, match.groups()))
    return version


def collect_versioned_candidates(label: str, home_fd: int, owner: int, layout: tuple[str, ...],
                                version_pattern: re.Pattern[str],
                                bin_parts: tuple[str, ...], candidates: list[int],
                                diagnostics: dict[str, int], candidate_labels: dict[int, str]) -> None:
    base_fd = home_fd
    opened: list[int] = []
    try:
        try:
            for part in layout:
                base_fd = open_directory_at(base_fd, part, owner)
                opened.append(base_fd)
        except FileNotFoundError:
            diagnostics['missing'] += 1
            return
        diagnostics['layout_present'] += 1
        versions = 0
        for name in os.listdir(base_fd):
            if version_pattern.fullmatch(name) is None:
                continue
            versions += 1
            version_fd = open_directory_at(base_fd, name, owner)
            try:
                bin_fd = version_fd
                bin_opened: list[int] = []
                try:
                    for part in bin_parts:
                        bin_fd = open_directory_at(bin_fd, part, owner)
                        bin_opened.append(bin_fd)
                    fd = open_node_at(bin_fd, owner)
                    candidates.append(fd)
                    candidate_labels[fd] = label
                    diagnostics['candidate'] += 1
                finally:
                    for fd in reversed(bin_opened):
                        os.close(fd)
            finally:
                os.close(version_fd)
        if versions == 0:
            diagnostics['no_matching_version'] += 1
    finally:
        for fd in reversed(opened):
            os.close(fd)


def resolve_probe_node(args: argparse.Namespace,
                       account: pwd.struct_passwd | None = None,
                       system_parts: tuple[tuple[str, ...], ...] = (
                           ('usr', 'local', 'bin'), ('usr', 'bin'),
                       )) -> tuple[int, tuple[int, int, int]]:
    account = account or pwd.getpwuid(args.probe_uid)
    home = pathlib.PurePosixPath(account.pw_dir)
    if not home.is_absolute() or '..' in home.parts:
        raise RuntimeError('probe_home')
    candidates: list[int] = []
    candidate_labels: dict[int, str] = {}
    diagnostics = {name: {'layout_present': 0, 'missing': 0, 'no_matching_version': 0,
                          'no_node': 0, 'candidate': 0, 'unsupported_version': 0,
                          'proc_fd_exec_failure': 0, 'version_failure': 0, 'exec_failure': 0}
                   for name in NODE_LAYOUTS}
    try:
        for parts in system_parts:
            directory_fd = -1
            try:
                directory_fd = open_directory_chain(parts, 0)
                label = 'system_usr_local_bin' if parts == ('usr', 'local', 'bin') else 'system_usr_bin'
                diagnostics[label]['layout_present'] += 1
                try:
                    fd = open_node_at(directory_fd, 0)
                    candidates.append(fd)
                    candidate_labels[fd] = label
                    diagnostics[label]['candidate'] += 1
                except RuntimeError:
                    diagnostics[label]['no_node'] += 1
                except OSError as error:
                    if error.errno not in (errno.ENOENT, errno.ELOOP):
                        raise
            finally:
                if directory_fd >= 0:
                    os.close(directory_fd)

        home_fd = open_directory_chain(tuple(part for part in home.parts if part != '/'), account.pw_uid)
        try:
            layouts = (
                ('nvm', ('.nvm', 'versions', 'node'), re.compile(r'v\d+\.\d+\.\d+'), ('bin',)),
                ('asdf', ('.asdf', 'installs', 'nodejs'), re.compile(r'\d+\.\d+\.\d+'), ('bin',)),
                ('mise', ('.local', 'share', 'mise', 'installs', 'node'), re.compile(r'\d+\.\d+\.\d+'), ('bin',)),
                ('fnm', ('.local', 'share', 'fnm', 'node-versions'), re.compile(r'v\d+\.\d+\.\d+'), ('installation', 'bin')),
            )
            for label, layout, version_pattern, bin_parts in layouts:
                collect_versioned_candidates(label, home_fd, account.pw_uid, layout,
                                             version_pattern, bin_parts, candidates,
                                             diagnostics[label], candidate_labels)
        finally:
            os.close(home_fd)

        identified: dict[tuple[int, int], tuple[int, tuple[int, int, int]]] = {}
        for fd in candidates:
            value = os.fstat(fd)
            identity = (value.st_dev, value.st_ino)
            try:
                version = probe_node_version(fd, args)
            except OSError:
                diagnostics[candidate_labels.get(fd, 'system_usr_bin')]['proc_fd_exec_failure'] += 1
                continue
            except subprocess.SubprocessError:
                diagnostics[candidate_labels.get(fd, 'system_usr_bin')]['exec_failure'] += 1
                continue
            except RuntimeError:
                diagnostics[candidate_labels.get(fd, 'system_usr_bin')]['version_failure'] += 1
                continue
            if version[0] >= 18:
                identified[identity] = (fd, version)
            else:
                diagnostics[candidate_labels.get(fd, 'system_usr_bin')]['unsupported_version'] += 1
        if not identified:
            raise NodeResolutionError('probe_node_resolution', diagnostics)
        best_version = max(version for _, version in identified.values())
        best = [(fd, version) for fd, version in identified.values() if version == best_version]
        if len(best) != 1:
            raise RuntimeError('probe_node_ambiguous')
        selected = best[0]
        for fd in candidates:
            if fd != selected[0]:
                os.close(fd)
        return selected
    except Exception:
        for fd in candidates:
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def read_lock_metadata() -> dict:
    fd = os.open(METADATA_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_gid != 0
                or stat.S_IMODE(before.st_mode) != 0o600):
            raise RuntimeError('lock_metadata_permissions')
        with os.fdopen(os.dup(fd), 'r', encoding='utf-8') as source:
            value = json.load(source)
        after = os.fstat(fd)
        current = METADATA_PATH.lstat()
        identity_before = (before.st_dev, before.st_ino, before.st_mode, before.st_uid, before.st_gid)
        identity_after = (after.st_dev, after.st_ino, after.st_mode, after.st_uid, after.st_gid)
        identity_current = (current.st_dev, current.st_ino, current.st_mode, current.st_uid, current.st_gid)
        if identity_before != identity_after or identity_after != identity_current:
            raise RuntimeError('lock_metadata_changed')
        return value
    finally:
        os.close(fd)


def validate_lock(args: argparse.Namespace) -> tuple[dict, str, str]:
    fd_raw = os.environ.get('SHARED_RELEASE_LOCK_CORE_FD', '')
    if not fd_raw.isdigit() or os.environ.get('SHARED_RELEASE_LOCK_ROOT') != str(LOCK_ROOT):
        raise RuntimeError('lock_environment')
    fd = int(fd_raw)
    fd_target = pathlib.Path(f'/proc/self/fd/{fd}').resolve(strict=True)
    if fd_target != LOCK_PATH or os.stat(fd).st_dev != LOCK_PATH.stat().st_dev or os.stat(fd).st_ino != LOCK_PATH.stat().st_ino:
        raise RuntimeError('lock_inode')
    metadata = exact(read_lock_metadata(), {
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
                (HELPER_ROOT, stat.S_IFDIR, 0, 0o755),
                (WORK_ROOT, stat.S_IFDIR, 0, 0o755)]
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


def current_runtime(args: argparse.Namespace) -> tuple[str, str, str]:
    current = APP_ROOT / 'current'
    if not current.is_symlink():
        raise RuntimeError('current_not_symlink')
    resolved = current.resolve(strict=True)
    releases = (APP_ROOT / 'releases').resolve(strict=True)
    if resolved.parent != releases:
        raise RuntimeError('current_escape')
    provenance = resolved / 'release-provenance.json'
    if not provenance.exists() and not provenance.is_symlink():
        if resolved.name != LEGACY_RELEASE_ID or not LEGACY_RUNTIME_SHA.startswith(resolved.name.rsplit('-', 1)[-1]):
            raise RuntimeError('legacy_runtime_identity')
        return LEGACY_RUNTIME_SHA, 'legacy-release-id', resolved.name
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
    release_match = re.fullmatch(r'[A-Za-z0-9._-]+-([a-f0-9]{40})', resolved.name)
    if release_match is None or release_match.group(1) != value['candidateSha']:
        raise RuntimeError('runtime_release_identity')
    return value['candidateSha'], 'release-provenance', resolved.name


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
              args: argparse.Namespace, runtime: str, phase: str,
              stable_node: pathlib.Path) -> str:
    account = pwd.getpwuid(args.probe_uid)
    probe_dir = receipt.parent / f'.{receipt.stem}-probe'
    probe_dir.mkdir(mode=0o750)
    chown_as_root(probe_dir, 0, args.probe_gid)
    output_dir = probe_dir / 'output'
    output_dir.mkdir(mode=0o700)
    chown_as_root(output_dir, args.probe_uid, args.probe_gid)
    probe_copy = probe_dir / 'verify-shared-edge.sh'
    verifier_copy = probe_dir / 'verify-shared-edge-receipt.mjs'
    write_exclusive(probe_copy, probe.read_bytes(), 0o550)
    write_exclusive(verifier_copy, verifier.read_bytes(), 0o440)
    chown_as_root(probe_copy, 0, args.probe_gid)
    chown_as_root(verifier_copy, 0, args.probe_gid)
    actual = output_dir / 'receipt.json'
    environment = {'HOME': account.pw_dir, 'USER': account.pw_name, 'LOGNAME': account.pw_name,
        'LANG': 'C.UTF-8', 'PATH': f'{stable_node.parent}:/usr/local/bin:/usr/bin:/bin'}
    credentials = {}
    if os.geteuid() == 0:
        credentials = {'user': args.probe_uid, 'group': args.probe_gid,
            'extra_groups': os.getgrouplist(account.pw_name, args.probe_gid)}
    try:
        subprocess.run(['bash', str(probe_copy), '--owner-project', 'blog', '--owner-repo', args.repo,
            '--operation-sha', args.operation_sha, '--runtime-sha', runtime,
            '--workflow-run', str(args.installer_run), '--phase', phase, '--receipt', str(actual)],
            check=True, stdout=subprocess.DEVNULL, env=environment, **credentials)
        frozen = probe_dir / 'frozen-receipt.json'
        freeze_probe_receipt(actual, frozen, args)
        subprocess.run([str(stable_node), str(verifier_copy), str(frozen), 'success', 'blog',
            args.repo, args.operation_sha, runtime, str(args.installer_run), phase],
            check=True, stdout=subprocess.DEVNULL, env=environment, **credentials)
        os.replace(frozen, receipt)
        return sha256_file(receipt)
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


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

    work = pathlib.Path(tempfile.mkdtemp(prefix='.blog-control-plane-v2.', dir=WORK_ROOT))
    os.chmod(work, 0o710)
    chown_as_root(work, 0, args.probe_gid)
    previous = None
    stage = 'bundle'
    try:
        files = extract_bundle(args.bundle_fd, work)
        stage = 'runtime'
        runtime, runtime_evidence, runtime_release_id = current_runtime(args)
        stage = 'probe_runtime'
        probe_node_fd, _ = resolve_probe_node(args)
        try:
            stable_node, probe_node_sha = freeze_probe_node(probe_node_fd, work)
        finally:
            os.close(probe_node_fd)
        stage = 'before_probe'
        before = work / 'before.json'
        before_digest = run_probe(files['verify-shared-edge.sh'], files['verify-shared-edge-receipt.mjs'],
                                  before, args, runtime, 'pre-mutation', stable_node)
        stage = 'install'
        previous, installed = atomic_install(files)
        stage = 'after_probe'
        after = work / 'after.json'
        after_digest = run_probe(TARGETS['verify-shared-edge.sh'][1], TARGETS['verify-shared-edge-receipt.mjs'][1],
                                 after, args, runtime, 'pre-activation', stable_node)
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
            'runtime': {'fullSha': runtime, 'evidence': runtime_evidence,
                'releaseId': runtime_release_id},
            'source': {'rssSourceSha': args.rss_source_sha, 'wrapperSha256': WRAPPER_SHA,
                'installerTransactionSha256': args.installer_transaction_sha256,
                'coreSha256': CORE_SHA, 'transactionSha256': TARGETS['trusted-blog-remote-transaction.sh'][0],
                'probeNodeSha256': probe_node_sha,
                'probeSha256': TARGETS['verify-shared-edge.sh'][0],
                'probeVerifierSha256': TARGETS['verify-shared-edge-receipt.mjs'][0]},
            'installed': {'wrapperSha256': WRAPPER_SHA, 'coreSha256': CORE_SHA,
                'transactionSha256': installed['trusted-blog-remote-transaction.sh'],
                'probeSha256': installed['verify-shared-edge.sh'],
                'probeVerifierSha256': installed['verify-shared-edge-receipt.mjs']},
            'canonical': canonical,
            'lock': {'authority': 'live-flock', 'tokenSha256': token_digest,
                'audit': metadata['audit'], 'acquiredAt': metadata['acquiredAt']},
            'probes': {'before': {'phase': 'pre-mutation', 'runtimeSha': runtime,
                'receiptPath': str(before_path), 'sha256': before_digest},
                'after': {'phase': 'pre-activation', 'runtimeSha': runtime,
                    'receiptPath': str(after_path), 'sha256': after_digest}},
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
        if isinstance(error, NodeResolutionError):
            failure['nodeResolution'] = error.diagnostics
        audit_write(f'blog-control-plane-v2-{args.installer_run}-{args.installer_attempt}-failed.json', failure)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        detail = ''
        if isinstance(error, NodeResolutionError):
            detail = ':' + json.dumps(error.diagnostics, sort_keys=True, separators=(',', ':'))
        print(f'Blog control-plane installer failed closed: {type(error).__name__}:{error}{detail}', file=sys.stderr)
        raise SystemExit(64)

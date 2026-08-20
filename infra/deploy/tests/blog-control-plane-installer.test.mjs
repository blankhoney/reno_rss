import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { chmod, chown, copyFile, mkdir, mkdtemp, readFile, readdir, symlink, unlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  blogInstallerContract,
  verifyBlogInstallerInputs,
} from '../verify-blog-control-plane-installer-inputs.mjs';
import { verifyReceipt } from '../verify-blog-control-plane-install-receipt.mjs';

const workflow = readFileSync('.github/workflows/install-blog-control-plane.yml', 'utf8');

test('root-capable installer pins the reviewed Blog control plane and frozen artifact', () => {
  assert.match(workflow, /ref: 48a12b8cfd4c33a20d0d9ded922e5c8616a4b803/);
  assert.match(workflow, /CONTROL_PLANE_CI_RUN: '32351611647'/);
  assert.match(workflow, /OPERATION_SHA: e52ab44f8fb963a8f4d7cd1da326092f7972b2a8/);
  assert.match(workflow, /PRODUCER_RUN: '32339806061'/);
  assert.match(workflow, /ARTIFACT_ID: '9396499072'/);
  assert.match(workflow, /ARTIFACT_DIGEST: sha256:d5929e143256f83d9c2cb0d7254d1f1181e02045ac43916795857913aabd8378/);
  assert.match(workflow, /LEGACY_RUNTIME_SHA: 1667b3c891958c65426d9f3ed7dd0426f012cefc/);
  assert.match(workflow, /WRAPPER_SHA256: 2cf87eb5d54e626fd96bef70ea7b8543ef721a12bb610b31dd2578fb80c296a5/);
  assert.match(workflow, /CORE_SHA256: d54485e473c7729e74628105c0f0ca6f75bcc63e65d4b71c2f14f1e2f3b51429/);
  assert.match(workflow, /PROBE_SHA256: 8ad9f32344ab8007c503850a7c3b0f680ccf13cd3b06d95fa673221ac5d73766/);
  assert.match(workflow, /PROBE_VERIFIER_SHA256: 6102cf625a0b604c0d1ab52226139727fa287811928e4b33dc53f527dd75262c/);
  assert.doesNotMatch(workflow, /refs\/heads\/main.*blankhoney\/my_blog/);
});

test('installer authenticates RSS parity and executes only the canonical Blog installer path', () => {
  assert.match(workflow, /verify-shared-lock-source-contract\.mjs/);
  assert.match(workflow, /path: rss-canonical/);
  assert.match(workflow, /git -C rss-canonical rev-parse HEAD/);
  assert.match(workflow, /sha256sum "rss-canonical\/\$path"/);
  assert.match(workflow, /sha256sum "blog-control-plane\/\$path"/);
  assert.match(workflow, /RSS_SOURCE_SHA: 2b29cfafaafa0795401c7b226a159572f9af6729/);
  assert.match(workflow, /install-blog-control-plane-remote\.sh/);
  assert.match(workflow, /verify-blog-control-plane-install-receipt\.mjs/);
  assert.match(workflow, /blog-trusted-installer-\$\{\{ github\.run_id \}\}/);
  assert.equal((workflow.match(/secrets\.BLOG_REPO_READ_TOKEN/g) ?? []).length, 2);
  assert.doesNotMatch(workflow, /secrets\.GHCR_TOKEN/);
  assert.doesNotMatch(workflow, /ssh-keyscan|StrictHostKeyChecking=no/);
  const sshSetup = workflow.slice(workflow.indexOf('Set up trusted SSH'), workflow.indexOf('Install Blog control plane'));
  assert.match(sshSetup, /VPS_HOST: \$\{\{ secrets\.VPS_HOST \}\}/);
  assert.match(sshSetup, /VPS_PORT: \$\{\{ secrets\.VPS_PORT \}\}/);
  assert.match(sshSetup, /validate-known-hosts\.sh/);
  assert.doesNotMatch(workflow, /docker (?:compose )?build|release\.tar\.gz/);
});

test('remote installer enters the canonical wrapper before any remote write', () => {
  const remote = readFileSync('infra/deploy/install-blog-control-plane-remote.sh', 'utf8');
  const transaction = readFileSync('infra/deploy/install-blog-control-plane-transaction.py', 'utf8');
  assert.match(remote, /exec sudo -n bash -c/);
  assert.doesNotMatch(remote, /command -v node|INSTALLER_PROBE_NODE|INSTALLER_PROBE_UID|--probe-node|--probe-uid|--probe-gid/);
  assert.match(remote, /with-shared-release-lock\.sh/);
  assert.match(remote, /exec 8<&0/);
  assert.match(transaction, /'user': args\.probe_uid, 'group': args\.probe_gid/);
  assert.match(transaction, /os\.getgrouplist/);
  assert.match(transaction, /freeze_probe_node/);
  assert.match(transaction, /open_directory_at/);
  assert.match(transaction, /os\.O_DIRECTORY \| os\.O_NOFOLLOW/);
  assert.match(transaction, /pass_fds=\(fd,\)/);
  assert.match(transaction, /PROBE_ACCOUNT = 'deploy'/);
  assert.match(transaction, /pwd\.getpwnam\(PROBE_ACCOUNT\)/);
  assert.match(transaction, /account\.pw_uid <= 0 or account\.pw_gid < 0/);
  assert.doesNotMatch(transaction, /deploy_group not in os\.getgrouplist/);
  assert.match(transaction, /probe_identity_override/);
  assert.doesNotMatch(transaction, /-lic|\.pw_shell/);
  assert.match(transaction, /os\.open\(source, os\.O_RDONLY \| os\.O_NOFOLLOW\)/);
  assert.match(transaction, /file_identity\(before\) != file_identity\(after\)/);
  const remoteBody = remote.slice(remote.indexOf('remote="'), remote.indexOf('exec ssh'));
  assert.doesNotMatch(remoteBody, /mktemp|mkdir|tar\s+-x|cat\s*>/);
  assert.ok(transaction.indexOf('validate_lock(args)') < transaction.indexOf('tempfile.mkdtemp'));
  assert.match(transaction, /WORK_ROOT = pathlib\.Path\('\/run'\)/);
  assert.match(transaction, /tempfile\.mkdtemp\(prefix='\.blog-control-plane-v2\.', dir=WORK_ROOT\)/);
  assert.match(transaction, /os\.open\(METADATA_PATH, os\.O_RDONLY \| os\.O_NOFOLLOW\)/);
  assert.match(transaction, /identity_before != identity_after or identity_after != identity_current/);
  assert.ok(transaction.indexOf("'pre-mutation'") < transaction.indexOf('atomic_install(files)'));
  assert.ok(transaction.indexOf('atomic_install(files)') < transaction.indexOf("'pre-activation'"));
  assert.match(transaction, /restore\(previous\)/);
  assert.doesNotMatch(workflow, /docker (?:compose )?(?:pull|up)|migration|release\.tar\.gz/);
});

test('identity drift fails before trusted SSH or remote mutation', () => {
  const identity = workflow.indexOf('Authenticate the Blog control plane and frozen artifact');
  const rssCi = workflow.indexOf('Authenticate current RSS main CI');
  const ssh = workflow.indexOf('Set up trusted SSH');
  const install = workflow.indexOf('Install Blog control plane under the canonical lock');
  assert.ok(rssCi > 0 && identity > 0 && rssCi < ssh && identity < ssh && ssh < install);
  assert.match(workflow, /run\.path === '\.github\/workflows\/ci\.yml'/);
  assert.match(workflow, /matching\.length !== 1/);
  assert.match(workflow, /matching\[0\]\.conclusion !== 'success'/);
  assert.match(workflow, /verify-blog-control-plane-installer-inputs\.mjs/);
});

function fixtures() {
  const { repository, controlPlane, operation } = blogInstallerContract;
  const run = (identity) => ({
    id: identity.workflowRun,
    run_attempt: identity.workflowRunAttempt,
    name: 'ci', event: 'push', status: 'completed', conclusion: 'success', head_branch: 'main',
    workflow_id: 275301410, path: '.github/workflows/ci.yml',
    repository: { id: 1236581850, full_name: repository },
    head_repository: { id: 1236581850, full_name: repository }, head_sha: identity.fullSha,
  });
  return {
    control: run(controlPlane),
    producer: run(operation),
    artifact: {
      id: operation.artifactId, expired: false, name: operation.artifactName,
      digest: operation.artifactDigest,
      workflow_run: { id: operation.workflowRun, head_branch: 'main', head_sha: operation.fullSha },
    },
    runtime: { sha: blogInstallerContract.runtime.fullSha,
      html_url: `https://github.com/${repository}/commit/${blogInstallerContract.runtime.fullSha}` },
  };
}

test('metadata verifier accepts only the exact current control plane and frozen artifact', () => {
  const valid = fixtures();
  assert.doesNotThrow(() => verifyBlogInstallerInputs(valid.control, valid.producer, valid.artifact, valid.runtime));
  for (const mutate of [
    (value) => { value.control.head_sha = '0'.repeat(40); },
    (value) => { value.control.run_attempt = 2; },
    (value) => { value.control.path = '.github/workflows/release.yml'; },
    (value) => { value.producer.repository.id += 1; },
    (value) => { value.producer.id += 1; },
    (value) => { value.artifact.expired = true; },
    (value) => { value.artifact.digest = `sha256:${'0'.repeat(64)}`; },
    (value) => { value.artifact.workflow_run.head_sha = '0'.repeat(40); },
    (value) => { value.runtime.sha = '0'.repeat(40); },
  ]) {
    const value = structuredClone(valid);
    mutate(value);
    assert.throws(
      () => verifyBlogInstallerInputs(value.control, value.producer, value.artifact, value.runtime),
      /identity contract mismatch/,
    );
  }
});

test('strict v2 receipt binds dual identity, lock inode, hashes, and both probe digests', () => {
  const { repository, controlPlane, operation } = blogInstallerContract;
  const expected = {
    repo: repository, controlSha: controlPlane.fullSha, controlRun: String(controlPlane.workflowRun),
    controlAttempt: '1', operationSha: operation.fullSha, producerRun: String(operation.workflowRun),
    producerAttempt: '1', artifactId: String(operation.artifactId), artifactDigest: operation.artifactDigest,
    webDigest: `sha256:${'2'.repeat(64)}`, companionDigest: `sha256:${'3'.repeat(64)}`,
    installerRun: '7001', installerAttempt: '1', rssSourceSha: '2b29cfafaafa0795401c7b226a159572f9af6729',
    installerSha: '4'.repeat(40), wrapperSha: '5'.repeat(64), coreSha: '6'.repeat(64),
    transactionSha: '7'.repeat(64), probeSha: '8'.repeat(64), probeVerifierSha: '9'.repeat(64),
    installerTransactionSha: 'd'.repeat(64),
    probeNodeSha: 'e'.repeat(64),
    runtimeSha: '1667b3c891958c65426d9f3ed7dd0426f012cefc',
  };
  const receipt = {
    contractVersion: 2, event: 'blog-control-plane-installed',
    owner: { project: 'rss', repo: 'blankhoney/reno_rss' },
    controlPlane: { repo: repository, fullSha: controlPlane.fullSha,
      workflowRun: controlPlane.workflowRun, workflowRunAttempt: 1 },
    operation: { repo: repository, fullSha: operation.fullSha, workflowRun: operation.workflowRun,
      workflowRunAttempt: 1, artifactId: operation.artifactId, artifactDigest: operation.artifactDigest,
      webImageDigest: expected.webDigest, companionImageDigest: expected.companionDigest },
    installer: { repo: 'blankhoney/reno_rss', fullSha: expected.installerSha,
      workflowRun: 7001, workflowRunAttempt: 1 },
    runtime: { fullSha: expected.runtimeSha, evidence: 'legacy-release-id',
      releaseId: '20260719-201357-1667b3c' },
    source: { rssSourceSha: expected.rssSourceSha,
      installerTransactionSha256: expected.installerTransactionSha, wrapperSha256: expected.wrapperSha,
      coreSha256: expected.coreSha, transactionSha256: expected.transactionSha,
      probeNodeSha256: expected.probeNodeSha,
      probeSha256: expected.probeSha, probeVerifierSha256: expected.probeVerifierSha },
    installed: { wrapperSha256: expected.wrapperSha, coreSha256: expected.coreSha,
      transactionSha256: expected.transactionSha, probeSha256: expected.probeSha,
      probeVerifierSha256: expected.probeVerifierSha },
    canonical: { root: '/var/lib/reno-shared-vps/release-lock-v1',
      lockPath: '/var/lib/reno-shared-vps/release-lock-v1/release.lock', lockDeviceInode: '1:2',
      owner: 'root', group: 'reno-deploy', rootMode: '0770', lockMode: '0660', auditMode: '0770' },
    lock: { authority: 'live-flock', tokenSha256: 'a'.repeat(64),
      audit: { state: 'held', lastEvent: 'acquired' }, acquiredAt: '2026-08-20T01:02:03Z' },
    probes: {
      before: { phase: 'pre-mutation', runtimeSha: expected.runtimeSha, receiptPath: '/var/lib/reno-shared-vps/release-lock-v1/audit/blog-control-plane-v2-7001-1-before.json', sha256: 'b'.repeat(64) },
      after: { phase: 'pre-activation', runtimeSha: expected.runtimeSha, receiptPath: '/var/lib/reno-shared-vps/release-lock-v1/audit/blog-control-plane-v2-7001-1-after.json', sha256: 'c'.repeat(64) },
    }, timestamp: '2026-08-20T01:03:04Z',
  };
  assert.doesNotThrow(() => verifyReceipt(receipt, expected));
  const provenanceReceipt = structuredClone(receipt);
  provenanceReceipt.runtime = { fullSha: expected.operationSha, evidence: 'release-provenance',
    releaseId: `prod-${expected.operationSha}` };
  provenanceReceipt.probes.before.runtimeSha = expected.operationSha;
  provenanceReceipt.probes.after.runtimeSha = expected.operationSha;
  assert.doesNotThrow(() => verifyReceipt(provenanceReceipt, expected));
  for (const mutate of [
    (value) => { value.controlPlane.fullSha = value.operation.fullSha; },
    (value) => { value.installed.probeSha256 = '0'.repeat(64); },
    (value) => { value.source.probeNodeSha256 = 'short'; },
    (value) => { value.canonical.lockPath = '/srv/brianstorm/shared/release-lock-v1/release.lock'; },
    (value) => { value.probes.after.phase = 'post-activation'; },
    (value) => { value.runtime.fullSha = value.operation.fullSha; },
    (value) => { value.runtime.evidence = 'release-provenance'; },
    (value) => { value.lock.audit.state = 'released'; },
    (value) => { value.unknown = true; },
  ]) {
    const changed = structuredClone(receipt); mutate(changed);
    assert.throws(() => verifyReceipt(changed, expected), /receipt rejected/);
  }
});

test('Linux deploy runtime resolver uses only fixed install roots and the highest supported version', {
  skip: process.platform !== 'linux',
}, async () => {
  const root = await mkdtemp(path.join(os.homedir(), '.rss-blog-node-resolver-'));
  const fakeNode = path.join(root, '.nvm', 'versions', 'node', 'v99.14.0', 'bin', 'node');
  const olderNode = path.join(root, '.nvm', 'versions', 'node', 'v20.19.0', 'bin', 'node');
  await mkdir(path.dirname(fakeNode), { recursive: true });
  await mkdir(path.dirname(olderNode), { recursive: true });
  await writeFile(fakeNode, '#!/bin/sh\nprintf "v99.14.0\\n"\n');
  await writeFile(olderNode, '#!/bin/sh\nprintf "v20.19.0\\n"\n');
  await chmod(fakeNode, 0o555);
  await chmod(olderNode, 0o555);
  const python = spawnSync('sh', ['-c', 'command -v python3'], { encoding: 'utf8' }).stdout.trim();
  const program = `import importlib.util, os, pathlib, types
spec=importlib.util.spec_from_file_location('installer', 'infra/deploy/install-blog-control-plane-transaction.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
account=types.SimpleNamespace(pw_dir='${root}', pw_name='fixture', pw_uid=${process.getuid()})
args=types.SimpleNamespace(probe_uid=${process.getuid()}, probe_gid=${process.getgid()})
fd,version=module.resolve_probe_node(args, account, ())
print(os.readlink(f'/proc/self/fd/{fd}'), '.'.join(map(str, version)))
os.close(fd)
`;
  const result = spawnSync(python, ['-c', program], { encoding: 'utf8', env: { ...process.env, PATH: '/caller-path-without-node' } });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), `${fakeNode} 99.14.0`);
  const unsafeSystemDir = path.join(root, 'unsafe-system');
  await mkdir(unsafeSystemDir); await chmod(unsafeSystemDir, 0o777);
  const unsafeSystemProgram = program.replace('account, ())',
    `account, (tuple(part for part in pathlib.PurePosixPath('${unsafeSystemDir}').parts if part != '/'),))`);
  const unsafeSystem = spawnSync(python, ['-c', unsafeSystemProgram], { encoding: 'utf8' });
  assert.notEqual(unsafeSystem.status, 0);
  assert.match(unsafeSystem.stderr, /probe_node_directory/);
  const unsafe = path.join(root, '.nvm', 'versions', 'node', 'v99.0.0');
  await symlink(root, unsafe);
  const rejected = spawnSync(python, ['-c', program], { encoding: 'utf8' });
  assert.notEqual(rejected.status, 0);
});

test('Linux lock-held transaction runs both probes and restores every old byte on post-probe failure', {
  skip: process.platform !== 'linux',
}, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'rss-blog-installer-v2-'));
  await chmod(root, 0o755);
  const probeUid = process.getuid() === 0 ? 1000 : process.getuid();
  const probeGid = process.getgid() === 0 ? 1000 : process.getgid();
  const lockGid = process.getuid() === 0 ? 65534 : probeGid;
  const lockGroup = spawnSync('id', ['-gn', String(lockGid)], { encoding: 'utf8' }).stdout.trim();
  const probeNode = spawnSync('readlink', ['-f', process.execPath], { encoding: 'utf8' }).stdout.trim();
  const lockRoot = path.join(root, 'lock');
  const audit = path.join(lockRoot, 'audit');
  const helper = path.join(root, 'helper');
  const releases = path.join(root, 'app', 'releases');
  const release = path.join(releases, '20260719-201357-1667b3c');
  await mkdir(path.join(helper, 'internal'), { recursive: true });
  await mkdir(audit, { recursive: true });
  await mkdir(release, { recursive: true });
  await writeFile(path.join(lockRoot, 'release.lock'), '');
  await chown(lockRoot, process.getuid(), lockGid);
  await chown(audit, process.getuid(), lockGid);
  await chown(path.join(lockRoot, 'release.lock'), process.getuid(), lockGid);
  await chmod(lockRoot, 0o770); await chmod(audit, 0o770);
  await chmod(path.join(lockRoot, 'release.lock'), 0o660); await chmod(helper, 0o755);
  await copyFile('infra/deploy/with-shared-release-lock.sh', path.join(helper, 'with-shared-release-lock.sh'));
  await copyFile('infra/deploy/internal/shared-release-lock-core.sh', path.join(helper, 'internal/shared-release-lock-core.sh'));
  await chown(path.join(helper, 'with-shared-release-lock.sh'), process.getuid(), process.getgid());
  await chown(path.join(helper, 'internal/shared-release-lock-core.sh'), process.getuid(), process.getgid());
  await chmod(path.join(helper, 'with-shared-release-lock.sh'), 0o555);
  await chmod(path.join(helper, 'internal/shared-release-lock-core.sh'), 0o555);
  await symlink(release, path.join(root, 'app', 'current'));

  const fixture = path.join(root, 'fixture'); await mkdir(fixture);
  const transaction = '#!/usr/bin/env bash\nexit 0\n';
  const probe = `#!/usr/bin/env bash
set -euo pipefail
phase=''; receipt=''; runtime=''; workflow=''
while (($#)); do case "$1" in --phase) phase="$2"; shift 2;; --runtime-sha) runtime="$2"; shift 2;; --workflow-run) workflow="$2"; shift 2;; --receipt) receipt="$2"; shift 2;; *) shift 2;; esac; done
printf 'probe diagnostic on stdout\\n'
[[ "$workflow" != 7002 || "$phase" != pre-activation ]] || exit 19
if [[ "$workflow" == 7007 ]]; then ln -s /etc/passwd "$receipt"; exit 0; fi
node_path="$(command -v node)"; node_sha="$(sha256sum "$node_path" | cut -d ' ' -f 1)"
printf '{"phase":"%s","runtime":"%s","uid":%s,"gid":%s,"groups":"%s","nodePath":"%s","nodeSha256":"%s"}\\n' \
  "$phase" "$runtime" "$(id -u)" "$(id -g)" "$(id -G)" "$node_path" "$node_sha" > "$receipt"
chmod 600 "$receipt"
`;
  const verifier = '#!/usr/bin/env node\nimport { readFileSync } from "node:fs";\nconsole.log("verifier diagnostic on stdout");\nconst value=JSON.parse(readFileSync(process.argv[2],"utf8"));\nprocess.exit(value.runtime===process.argv[7]&&value.phase===process.argv[9]?0:1);\n';
  const values = { 'trusted-blog-remote-transaction.sh': transaction,
    'verify-shared-edge.sh': probe, 'verify-shared-edge-receipt.mjs': verifier };
  for (const [name, body] of Object.entries(values)) await writeFile(path.join(fixture, name), body);
  const digest = (file) => spawnSync('sha256sum', [file], { encoding: 'utf8' }).stdout.split(/\s+/)[0];
  const tar = path.join(root, 'bundle.tar');
  assert.equal(spawnSync('tar', ['-C', fixture, '-cf', tar, ...Object.keys(values)]).status, 0);

  let source = await readFile('infra/deploy/install-blog-control-plane-transaction.py', 'utf8');
  source = source
    .replace("LOCK_ROOT = pathlib.Path('/var/lib/reno-shared-vps/release-lock-v1')", `LOCK_ROOT = pathlib.Path('${lockRoot}')`)
    .replace("HELPER_ROOT = pathlib.Path('/usr/local/lib/reno-shared-vps/release-lock-v1')", `HELPER_ROOT = pathlib.Path('${helper}')`)
    .replace("WORK_ROOT = pathlib.Path('/run')", `WORK_ROOT = pathlib.Path('${root}')`)
    .replace("APP_ROOT = pathlib.Path('/srv/brianstorm')", `APP_ROOT = pathlib.Path('${path.join(root, 'app')}')`)
    .replace("PROBE_ACCOUNT = 'deploy'", `PROBE_ACCOUNT = '${probeUid === 1000 ? 'node' : os.userInfo().username}'`)
    .replace("if os.geteuid() != 0 or os.uname().sysname != 'Linux':", "if os.uname().sysname != 'Linux':")
    .replaceAll("deploy_group = grp.getgrnam('reno-deploy').gr_gid", `deploy_group = ${lockGid}`)
    .replace('(HELPER_ROOT, stat.S_IFDIR, 0, 0o755)', '(HELPER_ROOT, stat.S_IFDIR, os.getgid(), 0o755)')
    .replace('(WORK_ROOT, stat.S_IFDIR, 0, 0o755)', '(WORK_ROOT, stat.S_IFDIR, os.getgid(), 0o755)')
    .replaceAll('value.st_uid != 0', 'value.st_uid != os.getuid()')
    .replaceAll('before.st_uid != 0', 'before.st_uid != os.getuid()')
    .replaceAll('before.st_gid != 0', 'before.st_gid != os.getgid()')
    .replaceAll('group: int = 0', 'group: int = os.getgid()')
    .replaceAll('owner: int = 0', 'owner: int = os.getuid()')
    .replaceAll('os.chown(stage, 0, 0)', 'os.chown(stage, os.getuid(), os.getgid())')
    .replace('45c326fdd266311df5ac1114c4c47207429efc6b47bd795db4d6f06b0f602892', digest(path.join(fixture, 'trusted-blog-remote-transaction.sh')))
    .replace('8ad9f32344ab8007c503850a7c3b0f680ccf13cd3b06d95fa673221ac5d73766', digest(path.join(fixture, 'verify-shared-edge.sh')))
    .replace('6102cf625a0b604c0d1ab52226139727fa287811928e4b33dc53f527dd75262c', digest(path.join(fixture, 'verify-shared-edge-receipt.mjs')))
    .replace('probe_node_fd, _ = resolve_probe_node(args)', `probe_node_fd = os.open('${probeNode}', os.O_RDONLY | os.O_NOFOLLOW)`);
  const inner = path.join(root, 'inner.py'); await writeFile(inner, source);
  const core = path.resolve('infra/deploy/internal/shared-release-lock-core.sh');
  const baseArgs = ['--bundle-fd', '8', '--repo', 'blankhoney/my_blog',
    '--installer-transaction-sha256', 'd'.repeat(64),
    '--control-plane-sha', 'b'.repeat(40), '--operation-sha', 'a'.repeat(40),
    '--installer-attempt', '1', '--rss-source-sha', '2b29cfafaafa0795401c7b226a159572f9af6729',
    '--rss-installer-sha', 'c'.repeat(40), '--control-ci-run', '20', '--control-ci-attempt', '1',
    '--producer-run', '30', '--producer-attempt', '1', '--artifact-id', '40',
    '--artifact-digest', `sha256:${'4'.repeat(64)}`, '--web-image-digest', `sha256:${'5'.repeat(64)}`,
    '--companion-image-digest', `sha256:${'6'.repeat(64)}`];
  const run = (workflowRun, extraEnv = {}) => spawnSync('bash', ['-c',
    'exec 9>"$1"; flock -n 9; exec 8<"$2"; export SHARED_RELEASE_LOCK_CORE_FD=9 RENO_SHARED_RELEASE_BUNDLE_FD=8; shift 2; exec "$@"',
    '--', path.join(lockRoot, 'release.lock'), tar, core, '--owner', 'blog', '--repo', 'blankhoney/my_blog',
    '--sha', 'a'.repeat(40), '--run', String(workflowRun), '--ttl-seconds', '30', '--',
    'python3', inner, ...baseArgs, '--installer-run', String(workflowRun)], {
    encoding: 'utf8', env: { ...process.env, SHARED_RELEASE_LOCK_ROOT: lockRoot,
      SHARED_RELEASE_LOCK_OWNER: os.userInfo().username,
      SHARED_RELEASE_LOCK_GROUP: lockGroup, ...extraEnv },
  });

  const success = run(7001);
  assert.equal(success.status, 0, success.stderr);
  const legacyReceipt = JSON.parse(success.stdout);
  assert.deepEqual(legacyReceipt.runtime, { fullSha: '1667b3c891958c65426d9f3ed7dd0426f012cefc',
    evidence: 'legacy-release-id', releaseId: '20260719-201357-1667b3c' });
  const assertProbeEvidence = async (receiptPath, phase, runtime) => {
    const value = JSON.parse(await readFile(receiptPath, 'utf8'));
    assert.equal(value.phase, phase); assert.equal(value.runtime, runtime);
    assert.equal(value.uid, probeUid); assert.equal(value.gid, probeGid);
    const normalizeGroups = (groups) => groups.trim().split(/\s+/).map(Number).sort((a, b) => a - b);
    const expectedGroups = spawnSync('id', ['-G', String(probeUid)], { encoding: 'utf8' }).stdout;
    assert.deepEqual(normalizeGroups(value.groups), normalizeGroups(expectedGroups));
    if (process.getuid() === 0) assert.ok(!normalizeGroups(value.groups).includes(lockGid));
    assert.match(value.nodePath, /\/node$/); assert.notEqual(value.nodePath, probeNode);
    assert.equal(value.nodeSha256, digest(probeNode));
  };
  await assertProbeEvidence(legacyReceipt.probes.before.receiptPath, 'pre-mutation', legacyReceipt.runtime.fullSha);
  await assertProbeEvidence(legacyReceipt.probes.after.receiptPath, 'pre-activation', legacyReceipt.runtime.fullSha);
  for (const [name, body] of Object.entries(values)) assert.equal(await readFile(path.join(helper, name), 'utf8'), body);
  assert.equal((await readdir(audit)).filter((name) => name.endsWith('-installed.json')).length, 1);

  const overriddenIdentity = run(7008, { INSTALLER_PROBE_UID: String(probeUid) });
  assert.notEqual(overriddenIdentity.status, 0);
  assert.match(overriddenIdentity.stderr, /probe_identity_override/);
  assert.equal((await readdir(audit)).filter((name) => name.includes('7008-1-installed')).length, 0);

  const provenanceRelease = path.join(releases, `prod-${'a'.repeat(40)}`);
  await mkdir(provenanceRelease);
  await writeFile(path.join(provenanceRelease, 'release-provenance.json'), JSON.stringify({
    candidateSha: 'a'.repeat(40), companionImage: { id: `sha256:${'6'.repeat(64)}`,
      reference: `brianstorm-vps-companion:production-${'a'.repeat(40)}` }, imageArchiveSha256: '1'.repeat(64),
    repository: 'blankhoney/my_blog', schemaVersion: 1, sourceArchiveSha256: '2'.repeat(64),
    webImage: { id: `sha256:${'5'.repeat(64)}`, reference: `brianstorm-web:${'a'.repeat(40)}` }, workflowRunId: 30,
  }));
  await chmod(path.join(provenanceRelease, 'release-provenance.json'), 0o644);
  await unlink(path.join(root, 'app', 'current'));
  await symlink(provenanceRelease, path.join(root, 'app', 'current'));
  const provenanceSuccess = run(7006);
  assert.equal(provenanceSuccess.status, 0, provenanceSuccess.stderr);
  const provenanceReceipt = JSON.parse(provenanceSuccess.stdout);
  assert.deepEqual(provenanceReceipt.runtime, { fullSha: 'a'.repeat(40),
    evidence: 'release-provenance', releaseId: `prod-${'a'.repeat(40)}` });
  await assertProbeEvidence(provenanceReceipt.probes.before.receiptPath, 'pre-mutation', 'a'.repeat(40));
  await assertProbeEvidence(provenanceReceipt.probes.after.receiptPath, 'pre-activation', 'a'.repeat(40));
  await unlink(path.join(root, 'app', 'current'));
  await symlink(release, path.join(root, 'app', 'current'));

  const old = { 'trusted-blog-remote-transaction.sh': 'old transaction\n',
    'verify-shared-edge.sh': 'old probe\n', 'verify-shared-edge-receipt.mjs': 'old verifier\n' };
  for (const [name, body] of Object.entries(old)) {
    await chmod(path.join(helper, name), 0o755);
    await writeFile(path.join(helper, name), body); await chmod(path.join(helper, name), 0o555);
  }
  const failed = run(7002);
  assert.notEqual(failed.status, 0);
  for (const [name, body] of Object.entries(old)) assert.equal(await readFile(path.join(helper, name), 'utf8'), body);
  assert.equal((await readdir(audit)).filter((name) => name.includes('7002-1-failed')).length, 1);

  const poison = path.join(root, 'poison-metadata.json');
  await writeFile(poison, '{}'); await chmod(poison, 0o600);
  const poisoned = spawnSync('bash', ['-c',
    'exec 9>"$1"; flock -n 9; exec 8<"$2"; export SHARED_RELEASE_LOCK_CORE_FD=9 RENO_SHARED_RELEASE_BUNDLE_FD=8; shift 2; exec "$@"',
    '--', path.join(lockRoot, 'release.lock'), tar, core, '--owner', 'blog', '--repo', 'blankhoney/my_blog',
    '--sha', 'a'.repeat(40), '--run', '7003', '--ttl-seconds', '30', '--',
    'bash', '-c', 'rm -- "$1"; ln -s "$2" "$1"; shift 2; exec "$@"', 'bash',
    path.join(lockRoot, 'metadata.json'), poison, 'python3', inner, ...baseArgs, '--installer-run', '7003'], {
    encoding: 'utf8', env: { ...process.env,
      SHARED_RELEASE_LOCK_ROOT: lockRoot, SHARED_RELEASE_LOCK_OWNER: os.userInfo().username,
      SHARED_RELEASE_LOCK_GROUP: lockGroup,
      RENO_SHARED_RELEASE_BUNDLE_FD: '8' },
  });
  assert.notEqual(poisoned.status, 0);
  assert.match(poisoned.stderr, /failed closed/);
  assert.equal((await readdir(audit)).filter((name) => name.includes('7003-1-installed')).length, 0);
  for (const [name, body] of Object.entries(old)) assert.equal(await readFile(path.join(helper, name), 'utf8'), body);

  const wrongMode = spawnSync('bash', ['-c',
    'exec 9>"$1"; flock -n 9; exec 8<"$2"; export SHARED_RELEASE_LOCK_CORE_FD=9 RENO_SHARED_RELEASE_BUNDLE_FD=8; shift 2; exec "$@"',
    '--', path.join(lockRoot, 'release.lock'), tar, core, '--owner', 'blog', '--repo', 'blankhoney/my_blog',
    '--sha', 'a'.repeat(40), '--run', '7004', '--ttl-seconds', '30', '--',
    'bash', '-c', 'rm -- "$1"; cp "$2" "$1"; chmod 0644 "$1"; shift 2; exec "$@"', 'bash',
    path.join(lockRoot, 'metadata.json'), poison, 'python3', inner, ...baseArgs, '--installer-run', '7004'], {
    encoding: 'utf8', env: { ...process.env,
      SHARED_RELEASE_LOCK_ROOT: lockRoot, SHARED_RELEASE_LOCK_OWNER: os.userInfo().username,
      SHARED_RELEASE_LOCK_GROUP: lockGroup,
      RENO_SHARED_RELEASE_BUNDLE_FD: '8' },
  });
  assert.notEqual(wrongMode.status, 0);
  assert.match(wrongMode.stderr, /failed closed/);
  assert.equal((await readdir(audit)).filter((name) => name.includes('7004-1-installed')).length, 0);

  const mismatchedLegacy = path.join(releases, '20260719-201357-deadbee');
  await mkdir(mismatchedLegacy);
  await unlink(path.join(root, 'app', 'current'));
  await symlink(mismatchedLegacy, path.join(root, 'app', 'current'));
  const mismatched = run(7005);
  assert.notEqual(mismatched.status, 0);
  assert.match(mismatched.stderr, /failed closed/);
  assert.equal((await readdir(audit)).filter((name) => name.includes('7005-1-installed')).length, 0);
  for (const [name, body] of Object.entries(old)) assert.equal(await readFile(path.join(helper, name), 'utf8'), body);

  await unlink(path.join(root, 'app', 'current'));
  await symlink(release, path.join(root, 'app', 'current'));
  const symlinkReceipt = run(7007);
  assert.notEqual(symlinkReceipt.status, 0);
  assert.match(symlinkReceipt.stderr, /failed closed/);
  assert.equal((await readdir(audit)).filter((name) => name.includes('7007-1-installed')).length, 0);
  for (const [name, body] of Object.entries(old)) assert.equal(await readFile(path.join(helper, name), 'utf8'), body);
});

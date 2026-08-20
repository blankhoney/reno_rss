import assert from 'node:assert/strict';
import { chmod, mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const builder = path.join(repoRoot, '.github/scripts/build-trusted-deploy-bundle.sh');
const transaction = path.join(repoRoot, '.github/scripts/remote-deploy.sh');
const operationSha = 'a'.repeat(40);
const controlPlaneSha = 'd'.repeat(40);
const rollbackFrom = 'b'.repeat(40);
const digest = 'c'.repeat(64);
const repo = 'blankhoney/reno_rss';

function builderArguments(requestType = 'deploy', environment = 'staging') {
  return [
    '--request-type', requestType,
    '--environment', environment,
    '--owner-project', 'rss',
    '--owner-repo', repo,
    '--operation-sha', operationSha,
    '--control-plane-sha', controlPlaneSha,
    '--workflow-run', '321',
    '--image-tag', `sha-${operationSha}`,
    '--web-image', `ghcr.io/${repo}/ai-reader-web@sha256:${digest}`,
    '--api-image', `ghcr.io/${repo}/ai-reader-api@sha256:${digest}`,
    '--worker-image', `ghcr.io/${repo}/ai-reader-worker@sha256:${digest}`,
  ];
}

function buildBundle(requestType = 'deploy', environment = 'staging') {
  const result = spawnSync(builder, builderArguments(requestType, environment), { cwd: repoRoot });
  assert.equal(result.status, 0, result.stderr.toString());
  return result.stdout;
}

test('builder emits one strict secret-free manifest with full-SHA digest references', () => {
  const bundle = buildBundle('rollback');
  const result = spawnSync('tar', ['-xOf', '-', 'manifest.json'], { input: bundle });
  assert.equal(result.status, 0, result.stderr.toString());
  const manifest = JSON.parse(result.stdout.toString());
  assert.deepEqual(Object.keys(manifest).sort(), [
    'contractVersion', 'controlPlane', 'environment', 'imageTag', 'images', 'operation',
    'owner', 'requestType', 'workflowRun',
  ]);
  assert.equal(manifest.requestType, 'rollback');
  assert.equal(manifest.operation.fullSha, operationSha);
  assert.equal(manifest.controlPlane.fullSha, controlPlaneSha);
  assert.equal(manifest.imageTag, `sha-${operationSha}`);
  assert.equal(JSON.stringify(manifest).includes('token'), false);
  assert.match(manifest.images.web, /@sha256:[0-9a-f]{64}$/);
  const members = spawnSync('tar', ['-tf', '-'], { input: bundle, encoding: 'utf8' });
  assert.equal(members.status, 0, members.stderr);
  assert.deepEqual(members.stdout.trim().split('\n').sort(), [
    'ensure-shared-edge.sh', 'manifest.json', 'rollback-state.sh', 'verify-shared-edge-receipt.mjs',
    'verify-shared-edge.sh',
  ]);
});

test('builder rejects legacy tags, tag-only images, and unknown request types', () => {
  for (const replacement of [
    ['--image-tag', 'sha-aaaaaaa'],
    ['--web-image', `ghcr.io/${repo}/ai-reader-web:sha-${operationSha}`],
    ['--request-type', 'compensate'],
  ]) {
    const args = builderArguments();
    args[args.indexOf(replacement[0]) + 1] = replacement[1];
    const result = spawnSync(builder, args, { cwd: repoRoot });
    assert.notEqual(result.status, 0);
  }
});

test('transaction source gates its first mutation on the inherited canonical flock', async () => {
  const source = await readFile(transaction, 'utf8');
  const assertion = source.indexOf('assert_shared_lock_held');
  const assertionCall = source.indexOf('\nassert_shared_lock_held', assertion);
  const firstMutation = source.indexOf('transaction_dir="$(mktemp', assertionCall);
  assert.ok(assertionCall > assertion);
  assert.ok(firstMutation > assertionCall);
  assert.equal(source.includes(': "${GHCR_TOKEN_B64:'), false);
  assert.match(source, /RENO_SHARED_RELEASE_BUNDLE_FD/);
  assert.match(source, /read -r -u "\$bundle_fd" credential_frame/);
  assert.match(source, /"\$bundle_path" "\$MAX_BUNDLE_BYTES" <&"\$bundle_fd"/);
  assert.match(source, /run_probe pre-mutation[\s\S]*locked_mutation/);
  assert.match(source, /locked_mutation\(\)[\s\S]*prepare_control_plane[\s\S]*run_production_prebackup[\s\S]*ensure_shared_edge[\s\S]*run_probe pre-activation/);
  assert.match(source, /rollback_state_compensate/);
});

async function executable(file, body) {
  await writeFile(file, body, { mode: 0o755 });
  await chmod(file, 0o755);
}

async function linuxFixture(requestType, {
  environment = 'staging', failTarget = false, failPostProbe = false, failBackup = false,
  preserveBundleFd = true,
} = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'trusted-remote-'));
  const lockRoot = path.join(root, 'lock');
  const app = path.join(root, 'app');
  const bin = path.join(root, 'bin');
  const state = path.join(root, 'runtime');
  const log = path.join(root, 'calls.log');
  const marker = path.join(root, 'first-mutation-lock-held');
  const edgeState = path.join(root, 'edge-state');
  const backupDir = path.join(app, 'backup', 'fixture');
  await mkdir(path.join(lockRoot, 'audit'), { recursive: true });
  await mkdir(path.join(app, '.git'), { recursive: true });
  await mkdir(path.join(app, 'infra/deploy'), { recursive: true });
  await mkdir(path.join(app, 'infra/scripts'), { recursive: true });
  await mkdir(bin);
  await writeFile(path.join(lockRoot, 'release.lock'), '');
  await writeFile(state, `${rollbackFrom}\n`);
  await writeFile(log, '');
  await writeFile(edgeState, 'attached\n');
  await writeFile(path.join(root, 'grafts'), '');
  const metadata = {
    contractVersion: 1, owner: 'rss', repo, fullSha: operationSha, workflowRun: 321,
    token: 'f'.repeat(64), acquiredAt: '2026-08-20T00:00:00Z', expiresAt: '2026-08-20T01:00:00Z',
    pid: 1, childPid: 2, childPgid: 2,
    lock: { authority: 'live-flock', ttl: 'diagnostic-only', path: `${lockRoot}/release.lock` },
    audit: { state: 'held', lastEvent: 'acquired' },
  };
  await writeFile(path.join(lockRoot, 'metadata.json'), `${JSON.stringify(metadata)}\n`);

  const transformed = (await readFile(transaction, 'utf8'))
    .replaceAll('/var/lib/reno-shared-vps/release-lock-v1', lockRoot);
  const transactionCopy = path.join(root, 'trusted-remote-deploy.sh');
  await executable(transactionCopy, transformed);
  await executable(path.join(bin, 'mktemp'), `#!/usr/bin/env bash
set -euo pipefail
if /usr/bin/flock -n "$LOCK_PATH_TEST" true 2>/dev/null; then exit 91; fi
printf 'held\n' > "$LOCK_MARKER_TEST"
exec /usr/bin/mktemp "$@"
`);
  await executable(path.join(bin, 'git'), `#!/usr/bin/env bash
set -euo pipefail
printf 'git %s\n' "$*" >> "$CALL_LOG"
case "$*" in
  *'status --porcelain'*) exit 0 ;;
  *'rev-parse --git-path info/grafts'*) printf '%s\n' "$GRAFTS_TEST" ;;
  *'rev-parse --is-shallow-repository'*) printf 'false\n' ;;
  *'rev-parse --verify'*) printf '%s\n' "$CONTROL_PLANE_SHA_TEST" ;;
  *'rev-parse HEAD'*) printf '%s\n' "$CONTROL_PLANE_SHA_TEST" ;;
  *) exit 0 ;;
esac
`);
  await executable(path.join(bin, 'docker'), `#!/usr/bin/env bash
set -euo pipefail
printf 'docker %s\n' "$*" >> "$CALL_LOG"
if [[ "\${1:-}" == login ]]; then cat >/dev/null; exit 0; fi
if [[ "\${1:-}" == pull ]]; then exit 0; fi
if [[ "\${1:-} \${2:-}" == 'image inspect' ]]; then printf '%s\n' "$OPERATION_SHA_TEST"; exit 0; fi
if [[ "\${1:-}" == inspect ]]; then
  runtime="$(tr -d '\n' < "$RUNTIME_STATE")"
  format="\${3:-}"; container="\${4:-}"
  if [[ "$format" == *Config.Image* ]]; then
    case "$container" in *reader-web*) package=ai-reader-web;; *api*) package=ai-reader-api;; *) package=ai-reader-worker;; esac
    printf 'ghcr.io/%s/%s@sha256:%s\n' "$OWNER_REPO_TEST" "$package" "$ROLLBACK_DIGEST_TEST"
  else printf '%s\n' "$runtime"; fi
  exit 0
fi
exit 0
`);
  await executable(path.join(app, 'infra/deploy/verify-shared-edge.sh'), `#!/usr/bin/env bash
set -euo pipefail
printf 'probe %s\n' "$*" >> "$CALL_LOG"
phase='';receipt=''
while (($#)); do case "$1" in --phase) phase="$2";shift 2;; --receipt) receipt="$2";shift 2;; *) shift;; esac;done
[[ "$(tr -d '\n' < "$EDGE_STATE_TEST")" == attached ]] || exit 22
[[ -n "$receipt" ]]||exit 2
if [[ "\${FAIL_POST_PROBE_TEST:-0}" == 1 && "$phase" =~ ^post- && "$phase" != post-compensation && ! -e "$FAIL_POST_ONCE_TEST" ]];then
  : > "$FAIL_POST_ONCE_TEST";printf '{}\n' > "$receipt";exit 23
fi
printf '{}\n' > "$receipt";exit 0
`);
  await executable(path.join(app, 'infra/deploy/verify-shared-edge-receipt.mjs'), `#!/usr/bin/env node
import { existsSync } from 'node:fs';
const [receipt, expectedStatus] = process.argv.slice(2);
if (!existsSync(receipt) || !['success', 'failure'].includes(expectedStatus)) process.exit(1);
`);
  await executable(path.join(app, 'infra/deploy/ensure-shared-edge.sh'), `#!/usr/bin/env bash
set -euo pipefail
printf 'ensure lock=%s\n' "$(test -f "$LOCK_MARKER_TEST" && printf held)" >> "$CALL_LOG"
printf 'attached\n' > "$EDGE_STATE_TEST"
`);
  await executable(path.join(app, 'infra/scripts/deploy.sh'), `#!/usr/bin/env bash
set -euo pipefail
sha="\${2#sha-}";printf 'activate %s\n' "$sha" >> "$CALL_LOG";printf '%s\n' "$sha" > "$RUNTIME_STATE";printf 'broken\n' > "$EDGE_STATE_TEST"
if [[ "\${FAIL_TARGET_TEST:-0}" == 1 && "$sha" == "$OPERATION_SHA_TEST" && ! -e "$FAIL_ONCE_TEST" ]]; then : > "$FAIL_ONCE_TEST";exit 19;fi
`);
  await executable(path.join(app, 'infra/scripts/backup.sh'), `#!/usr/bin/env bash
set -euo pipefail
printf 'backup-start %s\n' "\${1:-}" >> "$CALL_LOG"
[[ "\${FAIL_BACKUP_TEST:-0}" != 1 ]] || exit 47
mkdir -p "$BACKUP_DIR_TEST"
printf 'fixture backup\n' > "$BACKUP_DIR_TEST/scoring.dump"
sha256sum "$BACKUP_DIR_TEST/scoring.dump" > "$BACKUP_DIR_TEST/checksums.txt"
printf 'BACKUP_DIR=%s\n' "$BACKUP_DIR_TEST"
printf 'BACKUP_SHA256_FILE=%s\n' "$BACKUP_DIR_TEST/checksums.txt"
printf 'backup-complete\n' >> "$CALL_LOG"
`);
  await executable(path.join(app, 'infra/scripts/smoke-test.sh'), '#!/usr/bin/env bash\nexit 0\n');
  await executable(path.join(app, 'infra/scripts/staging-runtime-proof.sh'), '#!/usr/bin/env bash\nexit 0\n');
  await writeFile(path.join(app, 'infra/deploy/rollback-state.sh'), await readFile(path.join(repoRoot, 'infra/deploy/rollback-state.sh')));

  const bundleDir = path.join(root, 'bundle');
  await mkdir(bundleDir);
  const extracted = spawnSync('tar', ['-xf', '-', '-C', bundleDir], { input: buildBundle(requestType, environment) });
  assert.equal(extracted.status, 0, extracted.stderr.toString());
  // Production contract scripts are intentionally archived read-only (0555).
  // Replace the extracted members rather than relying on root being able to
  // overwrite them, so this fixture behaves the same for an unprivileged CI user.
  await rm(path.join(bundleDir, 'verify-shared-edge.sh'));
  await rm(path.join(bundleDir, 'verify-shared-edge-receipt.mjs'));
  await rm(path.join(bundleDir, 'ensure-shared-edge.sh'));
  await rm(path.join(bundleDir, 'rollback-state.sh'));
  await writeFile(path.join(bundleDir, 'verify-shared-edge.sh'), await readFile(path.join(app, 'infra/deploy/verify-shared-edge.sh')));
  await writeFile(path.join(bundleDir, 'verify-shared-edge-receipt.mjs'), await readFile(path.join(app, 'infra/deploy/verify-shared-edge-receipt.mjs')));
  await writeFile(path.join(bundleDir, 'ensure-shared-edge.sh'), await readFile(path.join(app, 'infra/deploy/ensure-shared-edge.sh')));
  await writeFile(path.join(bundleDir, 'rollback-state.sh'), await readFile(path.join(repoRoot, 'infra/deploy/rollback-state.sh')));
  const packed = spawnSync('tar', ['-cf', '-', 'manifest.json', 'verify-shared-edge.sh', 'verify-shared-edge-receipt.mjs', 'ensure-shared-edge.sh', 'rollback-state.sh'], { cwd: bundleDir });
  assert.equal(packed.status, 0, packed.stderr.toString());
  const bundle = packed.stdout;
  const transport = Buffer.concat([Buffer.from('GHCR_TOKEN_B64 dG9rZW4=\n'), bundle]);
  // Match the production core: the transaction is a background session, so
  // fd 0 is not a safe transport.  The remote preflight must preserve the
  // authenticated stream on a dedicated inherited descriptor.
  const bundleSetup = preserveBundleFd
    ? 'exec 8<&0; export RENO_SHARED_RELEASE_BUNDLE_FD=8;'
    : 'unset RENO_SHARED_RELEASE_BUNDLE_FD;';
  const shell = `${bundleSetup} exec 9>"$LOCK_PATH_TEST"; /usr/bin/flock -n 9; export SHARED_RELEASE_LOCK_CORE_FD=9; setsid -- bash -c 'exec "$@"' bash "$TRANSACTION_TEST" & child=$!; wait "$child"`;
  const result = spawnSync('bash', ['-c', shell], {
    input: transport,
    env: {
      ...process.env, PATH: `${bin}:${process.env.PATH}`, VPS_APP_DIR: app, GHCR_USERNAME: 'blankhoney',
      LOCK_PATH_TEST: path.join(lockRoot, 'release.lock'), LOCK_MARKER_TEST: marker,
      TRANSACTION_TEST: transactionCopy, CALL_LOG: log, GRAFTS_TEST: path.join(root, 'grafts'),
      OPERATION_SHA_TEST: operationSha, RUNTIME_STATE: state, OWNER_REPO_TEST: repo,
      CONTROL_PLANE_SHA_TEST: controlPlaneSha, EDGE_STATE_TEST: edgeState,
      ROLLBACK_DIGEST_TEST: digest, FAIL_TARGET_TEST: failTarget ? '1' : '0',
      BACKUP_DIR_TEST: backupDir, FAIL_BACKUP_TEST: failBackup ? '1' : '0',
      FAIL_ONCE_TEST: path.join(root, 'failed-once'),
      FAIL_POST_PROBE_TEST: failPostProbe ? '1' : '0', FAIL_POST_ONCE_TEST: path.join(root, 'failed-post-once'),
    },
    encoding: 'utf8',
  });
  return {
    root, result,
    calls: await readFile(log, 'utf8'),
    runtime: (await readFile(state, 'utf8')).trim(),
    marker: await readFile(marker, 'utf8').catch(() => ''),
  };
}

test('Linux background session rejects a missing dedicated bundle FD before its first mutation', { skip: os.platform() !== 'linux' }, async () => {
  const item = await linuxFixture('deploy', { preserveBundleFd: false });
  try {
    assert.equal(item.result.status, 64);
    assert.match(item.result.stderr, /authenticated bundle FD 8 was not inherited/);
    assert.equal(item.marker, '');
    assert.equal(item.calls, '');
  } finally { await rm(item.root, { recursive: true, force: true }); }
});

test('Linux fixture holds the lock before temp/extract and wires deploy phases to actual runtime', { skip: os.platform() !== 'linux' }, async () => {
  const item = await linuxFixture('deploy');
  try {
    assert.equal(item.result.status, 0, item.result.stderr);
    assert.equal(item.marker.trim(), 'held');
    assert.equal(item.runtime, operationSha);
    assert.match(item.calls, new RegExp(`probe .*--phase pre-mutation --runtime-sha ${rollbackFrom}`));
    assert.match(item.calls, /ensure lock=held/);
    assert.match(item.calls, new RegExp(`probe .*--phase pre-activation --runtime-sha ${rollbackFrom}`));
    assert.match(item.calls, new RegExp(`probe .*--phase post-activation --runtime-sha ${operationSha}`));
    assert.ok(item.calls.indexOf('--phase pre-activation') < item.calls.indexOf(`activate ${operationSha}`));
    assert.ok(item.calls.indexOf('--phase pre-mutation') < item.calls.indexOf('ensure lock=held'));
    assert.ok(item.calls.indexOf('ensure lock=held') < item.calls.indexOf('--phase pre-activation'));
    assert.ok(item.calls.indexOf('--no-replace-objects fetch') < item.calls.indexOf('ensure lock=held'));
    assert.ok(item.calls.indexOf('--phase pre-activation') < item.calls.indexOf('docker login'));
    assert.match(item.calls, new RegExp(`activate ${operationSha}[\\s\\S]*ensure lock=held[\\s\\S]*--phase post-activation`));
  } finally { await rm(item.root, { recursive: true, force: true }); }
});

test('Linux production transaction verifies backup before edge, login, pull, or activation', { skip: os.platform() !== 'linux' }, async () => {
  const item = await linuxFixture('deploy', { environment: 'prod' });
  try {
    assert.equal(item.result.status, 0, item.result.stderr);
    const backup = item.calls.indexOf('backup-complete');
    assert.ok(item.calls.indexOf('--phase pre-mutation') < backup);
    assert.ok(item.calls.indexOf('--no-replace-objects fetch') < backup);
    for (const mutation of ['ensure lock=held', 'docker login', 'docker pull', `activate ${operationSha}`]) {
      assert.ok(backup < item.calls.indexOf(mutation), `${mutation} must follow verified production backup`);
    }
  } finally { await rm(item.root, { recursive: true, force: true }); }
});

test('Linux production backup failure prevents edge, image, and activation mutations', { skip: os.platform() !== 'linux' }, async () => {
  const item = await linuxFixture('deploy', { environment: 'prod', failBackup: true });
  try {
    assert.notEqual(item.result.status, 0);
    assert.equal(item.runtime, rollbackFrom);
    assert.match(item.calls, /backup-start prod/);
    assert.doesNotMatch(item.calls, /ensure lock=held|docker login|docker pull|activate /);
  } finally { await rm(item.root, { recursive: true, force: true }); }
});

test('Linux rollback and failed deploy receipts bind operation and actual runtime correctly', { skip: os.platform() !== 'linux' }, async () => {
  const rollback = await linuxFixture('rollback');
  const failed = await linuxFixture('deploy', { failTarget: true });
  const failedPostProbe = await linuxFixture('deploy', { failPostProbe: true });
  try {
    assert.equal(rollback.result.status, 0, rollback.result.stderr);
    assert.match(rollback.calls, new RegExp(`checkout --detach ${controlPlaneSha}`));
    assert.doesNotMatch(rollback.calls, new RegExp(`checkout --detach ${operationSha}`));
    assert.match(rollback.calls, new RegExp(`--phase post-rollback --runtime-sha ${operationSha} .*--rollback-from-sha ${rollbackFrom} --rollback-target-sha ${operationSha}`));
    assert.equal(failed.result.status, 19, failed.result.stderr);
    assert.equal(failed.runtime, rollbackFrom);
    assert.match(failed.calls, new RegExp(`activate ${operationSha}[\\s\\S]*activate ${rollbackFrom}`));
    assert.match(failed.calls, new RegExp(`--phase post-compensation --runtime-sha ${rollbackFrom} .*--rollback-from-sha ${rollbackFrom} --rollback-target-sha ${operationSha}`));
    assert.equal(failedPostProbe.result.status, 23, failedPostProbe.result.stderr);
    assert.equal(failedPostProbe.runtime, rollbackFrom);
    assert.match(failedPostProbe.result.stdout, /TRUSTED_SHARED_EDGE_RECEIPT post-activation /);
    assert.match(failedPostProbe.result.stdout, /TRUSTED_SHARED_EDGE_RECEIPT post-compensation /);
    assert.match(failedPostProbe.calls, new RegExp(`--phase post-activation[\\s\\S]*activate ${rollbackFrom}[\\s\\S]*--phase post-compensation`));
  } finally {
    await rm(rollback.root, { recursive: true, force: true });
    await rm(failed.root, { recursive: true, force: true });
    await rm(failedPostProbe.root, { recursive: true, force: true });
  }
});

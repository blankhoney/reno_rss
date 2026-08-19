import assert from 'node:assert/strict';
import { execFile, execFileSync, spawn } from 'node:child_process';
import { chmod, mkdtemp, mkdir, readFile, readdir, rm, stat, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { kill as killProcess } from 'node:process';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const wrapper = resolve('infra/deploy/with-shared-release-lock.sh');
const core = resolve('infra/deploy/internal/shared-release-lock-core.sh');
const sha = 'a'.repeat(40);
const hasLinuxFlock = process.platform === 'linux' && (() => {
  try {
    execFileSync('bash', ['-c', 'command -v flock >/dev/null'], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
})();
const flockTest = (name, options, fn) => test(name, { ...options, skip: !hasLinuxFlock }, fn);

async function fixture() {
  const directory = await mkdtemp(join(tmpdir(), 'shared-release-lock-'));
  const root = join(directory, 'release-lock-v1');
  const lockPath = join(root, 'release.lock');
  const audit = join(root, 'audit');
  const owner = execFileSync('id', ['-un'], { encoding: 'utf8' }).trim();
  const group = execFileSync('id', ['-gn'], { encoding: 'utf8' }).trim();
  await mkdir(audit, { recursive: true });
  await writeFile(lockPath, '');
  await chmod(root, 0o770);
  await chmod(audit, 0o770);
  await chmod(lockPath, 0o660);
  return {
    directory,
    root,
    lockPath,
    metadata: join(root, 'metadata.json'),
    audit,
    environment: {
      ...process.env,
      SHARED_RELEASE_LOCK_ROOT: root,
      SHARED_RELEASE_LOCK_TEST_MODE: '1',
      SHARED_RELEASE_LOCK_OWNER: owner,
      SHARED_RELEASE_LOCK_GROUP: group,
    },
    args: (overrides = [], command = ['bash', '-c', 'true']) => [
      '--owner', 'rss', '--repo', 'blankhoney/reno_rss', '--sha', sha,
      '--run', '123', '--ttl-seconds', '30', ...overrides, '--', ...command,
    ],
  };
}

async function run(fix, overrides, command) {
  return execFileAsync('bash', [core, ...fix.args(overrides, command)], {
    env: fix.environment,
    encoding: 'utf8',
  });
}

async function reportFilesystemType(t, fix, filesystemType) {
  const bin = join(fix.directory, 'bin');
  const realStat = execFileSync('bash', ['-lc', 'command -v stat'], { encoding: 'utf8' }).trim();
  await mkdir(bin);
  const statShim = join(bin, 'stat');
  await writeFile(statShim, `#!/usr/bin/env bash
set -euo pipefail
if [[ "\${1:-}" == '-fLc' && "\${2:-}" == '%T' ]]; then
  printf '%s\\n' "\${SHARED_RELEASE_LOCK_TEST_FILESYSTEM_TYPE:?}"
  exit 0
fi
exec "\${SHARED_RELEASE_LOCK_REAL_STAT:?}" "$@"
`);
  await chmod(statShim, 0o755);
  t.after(() => rm(bin, { recursive: true, force: true }));
  return {
    ...fix,
    environment: {
      ...fix.environment,
      PATH: `${bin}:${fix.environment.PATH}`,
      SHARED_RELEASE_LOCK_REAL_STAT: realStat,
      SHARED_RELEASE_LOCK_TEST_FILESYSTEM_TYPE: filesystemType,
    },
  };
}

async function auditEvents(fix) {
  const names = (await readdir(fix.audit)).filter((name) => !name.startsWith('quarantine-'));
  return Promise.all(names.map(async (name) => JSON.parse(await readFile(join(fix.audit, name), 'utf8'))));
}

async function waitForFile(path) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      await stat(path);
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
  throw new Error(`timed out waiting for ${path}`);
}

const pause = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function markerStops(path) {
  const before = await readFile(path, 'utf8');
  await pause(180);
  assert.equal(await readFile(path, 'utf8'), before, 'mutation marker continued after release audit');
}

function waitForExit(process) {
  return new Promise((resolve) => process.once('exit', (code, signal) => resolve({ code, signal })));
}

function spawnLock(args, environment) {
  // Do not let a deliberately crashed wrapper's inherited stdio keep the
  // Node test worker alive. Process-group assertions below remain the
  // authority for proving that the mutation tree itself has stopped.
  return spawn('bash', args, { env: environment, stdio: 'ignore' });
}

async function transactionPgid(fix) {
  return JSON.parse(await readFile(fix.metadata, 'utf8')).childPgid;
}

async function assertProcessGroupStopped(pgid) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    let liveMember = false;
    for (const entry of await readdir('/proc')) {
      if (!/^\d+$/.test(entry)) continue;
      try {
        const raw = await readFile(`/proc/${entry}/stat`, 'utf8');
        const fields = raw.slice(raw.lastIndexOf(')') + 1).trim().split(/\s+/);
        if (Number(fields[2]) === pgid && fields[0] !== 'Z') {
          liveMember = true;
          break;
        }
      } catch (error) {
        if (error.code !== 'ENOENT' && error.code !== 'ESRCH') throw error;
      }
    }
    if (!liveMember) return;
    await pause(50);
  }
  assert.fail(`live transaction process group ${pgid} survived wrapper completion`);
}

flockTest('second owner fails closed while the first transaction holds the live flock', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const first = spawnLock([core, ...fix.args([], ['bash', '-c', 'sleep 2'])], fix.environment);
  const firstExited = waitForExit(first);
  await waitForFile(fix.metadata);
  const pgid = await transactionPgid(fix);
  await assert.rejects(
    run(fix, ['--owner', 'blog', '--repo', 'blankhoney/reno_blog'], ['bash', '-c', 'exit 99']),
    (error) => error.code === 75 && /another release transaction/.test(error.stderr),
  );
  assert.deepEqual(await firstExited, { code: 0, signal: null });
  await assertProcessGroupStopped(pgid);
});

flockTest('a live flock is authoritative even after its diagnostic TTL expires', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const first = spawnLock([core, ...fix.args(['--ttl-seconds', '1'], ['bash', '-c', 'sleep 3'])], fix.environment);
  const firstExited = waitForExit(first);
  await waitForFile(fix.metadata);
  const pgid = await transactionPgid(fix);
  await new Promise((resolve) => setTimeout(resolve, 1200));
  await assert.rejects(run(fix, [], ['bash', '-c', 'true']), (error) => error.code === 75);
  assert.deepEqual(await firstExited, { code: 0, signal: null });
  await assertProcessGroupStopped(pgid);
});

flockTest('only an exact owner and token can remove metadata; mismatch is audited and quarantined', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  await run(fix, [], ['bash', '-c', 'python3 - "$SHARED_RELEASE_LOCK_ROOT/metadata.json" <<\'PY\'\nimport json, sys\np = sys.argv[1]\nd = json.load(open(p))\nd["token"] = "0" * 64\nopen(p, "w").write(json.dumps(d))\nPY']);
  assert.equal((await stat(fix.metadata)).isFile(), true);
  const mismatchEvents = await auditEvents(fix);
  assert.equal(mismatchEvents.some((event) => event.event === 'release-refused'), true);

  await run(fix, [], ['bash', '-c', 'true']);
  const events = await auditEvents(fix);
  assert.equal(events.some((event) => event.event === 'quarantined-residual-metadata'), true);
  assert.equal(events.some((event) => event.event === 'released' && event.detail === 'exact-owner-token-match'), true);
});

flockTest('missing or invalid metadata refuses release, preserves evidence, and is quarantined by the next owner', {}, async (t) => {
  for (const mutation of [
    'rm -- "$SHARED_RELEASE_LOCK_ROOT/metadata.json"',
    'printf %s not-json > "$SHARED_RELEASE_LOCK_ROOT/metadata.json"',
  ]) {
    const fix = await fixture();
    t.after(() => rm(fix.directory, { recursive: true, force: true }));
    await run(fix, [], ['bash', '-c', mutation]);
    let events = await auditEvents(fix);
    assert.equal(
      events.some((event) => event.event === 'release-refused' && event.detail === 'metadata-mismatch-or-missing'),
      true,
    );

    await run(fix, [], ['bash', '-c', 'true']);
    events = await auditEvents(fix);
    if (mutation.startsWith('printf')) {
      assert.equal(events.some((event) => event.event === 'quarantined-residual-metadata'), true);
    }
    assert.equal(events.some((event) => event.event === 'released'), true);
  }
});

flockTest('core fails closed on a world-writable lock or a symbolic-linked audit path', {}, async (t) => {
  const writable = await fixture();
  t.after(() => rm(writable.directory, { recursive: true, force: true }));
  await chmod(writable.lockPath, 0o666);
  await assert.rejects(run(writable, [], ['true']), /owner, group, or mode/);

  const linked = await fixture();
  t.after(() => rm(linked.directory, { recursive: true, force: true }));
  await rm(linked.audit, { recursive: true });
  await symlink(linked.directory, linked.audit);
  await assert.rejects(run(linked, [], ['true']), /must not be a symbolic link/);
});

flockTest('core accepts the literal ext2/ext3 Linux stat output and rejects distributed or unknown filesystems', {}, async (t) => {
  const accepted = await reportFilesystemType(t, await fixture(), 'ext2/ext3');
  t.after(() => rm(accepted.directory, { recursive: true, force: true }));
  await run(accepted, [], ['bash', '-c', 'true']);

  for (const filesystemType of ['nfs', 'ceph', 'unrecognized-local-type']) {
    const rejected = await reportFilesystemType(t, await fixture(), filesystemType);
    t.after(() => rm(rejected.directory, { recursive: true, force: true }));
    await assert.rejects(
      run(rejected, [], ['bash', '-c', 'exit 91']),
      new RegExp(`local Linux flock filesystem, got ${filesystemType}`),
    );
  }
});

flockTest('SIGTERM keeps ownership through child termination and leaves an auditable release', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const process = spawnLock([core, ...fix.args([], ['bash', '-c', 'sleep 10'])], fix.environment);
  await waitForFile(fix.metadata);
  const pgid = await transactionPgid(fix);
  const exited = waitForExit(process);
  process.kill('SIGTERM');
  const result = await exited;
  assert.deepEqual(result, { code: 143, signal: null });
  const events = await auditEvents(fix);
  assert.equal(events.some((event) => event.event === 'signal' && event.detail === 'TERM'), true);
  assert.equal(events.some((event) => event.event === 'released'), true);
  await assert.rejects(stat(fix.metadata));
  await assertProcessGroupStopped(pgid);
});

flockTest('TERM, INT, and HUP retain the flock until a marker-writing transaction tree stops', {}, async (t) => {
  for (const signal of ['SIGTERM', 'SIGINT', 'SIGHUP']) {
    const fix = await fixture();
    t.after(() => rm(fix.directory, { recursive: true, force: true }));
    const marker = join(fix.directory, `${signal}.marker`);
    const childPid = join(fix.directory, `${signal}.child-pid`);
    const command = [
      'bash', '-c',
      'trap "sleep 0.25; exit 0" TERM INT HUP; (trap "sleep 0.25; exit 0" TERM INT HUP; while :; do date +%s%N >> "$1"; sleep 0.02; done) & worker=$!; echo $$ > "$2"; wait "$worker"',
      '--', marker, childPid,
    ];
    const process = spawnLock([core, ...fix.args([], command)], fix.environment);
    await waitForFile(marker);
    await waitForFile(fix.metadata);
    const pgid = await transactionPgid(fix);
    const exited = waitForExit(process);
    process.kill(signal);
    await pause(80);
    await assert.rejects(run(fix, ['--owner', 'blog', '--repo', 'blankhoney/reno_blog'], ['true']), (error) => error.code === 75);
    const expectedCode = { SIGTERM: 143, SIGINT: 130, SIGHUP: 129 }[signal];
    assert.deepEqual(await exited, { code: expectedCode, signal: null });
    const events = await auditEvents(fix);
    assert.equal(events.some((event) => event.event === 'signal' && event.detail === signal.slice(3)), true);
    assert.equal(events.some((event) => event.event === 'released'), true);
    await markerStops(marker);
    await assertProcessGroupStopped(pgid);
  }
});

flockTest('simultaneous parent and transaction signals do not release before mutations stop', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const marker = join(fix.directory, 'simultaneous.marker');
  const childPid = join(fix.directory, 'simultaneous.child-pid');
  const process = spawnLock([core, ...fix.args([], ['bash', '-c', 'echo $$ > "$2"; trap "exit 0" TERM; while :; do date +%s%N >> "$1"; sleep 0.02; done', '--', marker, childPid])], fix.environment);
  await waitForFile(marker);
  await waitForFile(childPid);
  await waitForFile(fix.metadata);
  process.kill('SIGTERM');
  killProcess(Number((await readFile(childPid, 'utf8')).trim()), 'SIGTERM');
  assert.deepEqual(await waitForExit(process), { code: 143, signal: null });
  const events = await auditEvents(fix);
  assert.equal(events.some((event) => event.event === 'released'), true);
  await markerStops(marker);
  await assertProcessGroupStopped(Number((await readFile(childPid, 'utf8')).trim()));
});

flockTest('a TERM-resistant transaction is escalated before its release is audited', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const marker = join(fix.directory, 'stubborn.marker');
  const process = spawnLock([core, ...fix.args([], ['bash', '-c', 'trap "" TERM INT HUP; while :; do date +%s%N >> "$1"; sleep 0.02; done', '--', marker])], fix.environment);
  await waitForFile(marker);
  await waitForFile(fix.metadata);
  const pgid = await transactionPgid(fix);
  process.kill('SIGTERM');
  assert.deepEqual(await waitForExit(process), { code: 143, signal: null });
  const events = await auditEvents(fix);
  assert.equal(events.some((event) => event.event === 'signal-escalated'), true);
  assert.equal(events.some((event) => event.event === 'released'), true);
  await markerStops(marker);
  await assertProcessGroupStopped(pgid);
});

flockTest('a crashed wrapper cannot release a transaction-held flock; recovery starts only after the child exits', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const process = spawnLock([core, ...fix.args([], ['bash', '-c', 'sleep 2'])], fix.environment);
  await waitForFile(fix.metadata);
  const pgid = await transactionPgid(fix);
  const exited = waitForExit(process);
  process.kill('SIGKILL');
  assert.deepEqual(await exited, { code: null, signal: 'SIGKILL' });
  await assert.rejects(run(fix, [], ['bash', '-c', 'true']), (error) => error.code === 75);

  // The child inherited the open flock FD.  It must finish before a later
  // transaction can recover the crash metadata; sleeping past its bounded
  // transaction demonstrates that recovery never steals a live mutation.
  await new Promise((resolve) => setTimeout(resolve, 2200));
  await run(fix, [], ['bash', '-c', 'true']);
  const events = await auditEvents(fix);
  assert.equal(events.some((event) => event.event === 'quarantined-residual-metadata'), true);
  await assertProcessGroupStopped(pgid);
});

flockTest('metadata schema and audit bind the complete v1 identity; source has no force deletion', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const captured = join(fix.root, 'captured.json');
  await run(fix, [], ['bash', '-c', 'cp "$SHARED_RELEASE_LOCK_ROOT/metadata.json" "$SHARED_RELEASE_LOCK_ROOT/captured.json"']);
  const metadata = JSON.parse(await readFile(captured, 'utf8'));
  assert.deepEqual(
    Object.keys(metadata).sort(),
    ['acquiredAt', 'audit', 'childPgid', 'childPid', 'contractVersion', 'expiresAt', 'fullSha', 'lock', 'owner', 'pid', 'repo', 'token', 'workflowRun'].sort(),
  );
  assert.equal(metadata.contractVersion, 1);
  assert.equal(metadata.owner, 'rss');
  assert.equal(metadata.repo, 'blankhoney/reno_rss');
  assert.equal(metadata.fullSha, sha);
  assert.equal(metadata.workflowRun, 123);
  assert.match(metadata.token, /^[0-9a-f]{64}$/);
  assert.equal(metadata.childPid, metadata.childPgid);
  assert.deepEqual(metadata.lock, { authority: 'live-flock', ttl: 'diagnostic-only', path: fix.lockPath });
  const events = await auditEvents(fix);
  const acquired = events.find((event) => event.event === 'acquired');
  assert.deepEqual(
    Object.keys(acquired).sort(),
    ['contractVersion', 'detail', 'event', 'fullSha', 'lockPath', 'owner', 'repo', 'timestamp', 'tokenSha256', 'workflowRun'].sort(),
  );
  assert.equal(acquired.contractVersion, 1);
  assert.equal(acquired.fullSha, sha);
  assert.equal(acquired.workflowRun, 123);
  const source = await readFile(core, 'utf8');
  assert.equal(source.includes('rm -f'), false);
  assert.match(source, /if metadata_matches_current_owner; then rm -- "\$METADATA_PATH"/);
});

flockTest('core holds an explicitly inherited canonical FD for the complete transaction', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const holder = spawnLock(
    ['-c', 'exec 9>"$1"; export SHARED_RELEASE_LOCK_CORE_FD=9; exec bash "$2" "${@:3}"', '--', fix.lockPath, core, ...fix.args([], ['bash', '-c', 'sleep 1'])],
    fix.environment,
  );
  const holderExited = waitForExit(holder);
  await waitForFile(fix.metadata);
  const pgid = await transactionPgid(fix);
  await assert.rejects(run(fix, [], ['true']), (error) => error.code === 75);
  assert.deepEqual(await holderExited, { code: 0, signal: null });
  await assertProcessGroupStopped(pgid);
});

flockTest('core rejects an inherited FD whose inode is not the configured canonical lock', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const wrongLock = join(fix.directory, 'wrong.lock');
  await writeFile(wrongLock, '');
  await assert.rejects(
    execFileAsync(
      'bash',
      ['-c', 'exec 9>"$1"; export SHARED_RELEASE_LOCK_CORE_FD=9; exec bash "$2" "${@:3}"', '--', wrongLock, core, ...fix.args()],
      { env: fix.environment, encoding: 'utf8' },
    ),
    /does not reference the configured release\.lock/,
  );
});

test('public wrapper owns the canonical root and rejects every caller path or test override', async () => {
  const base = ['--owner', 'rss', '--repo', 'blankhoney/reno_rss', '--sha', sha, '--run', '123', '--ttl-seconds', '30', '--', 'true'];
  for (const environment of [
    { ...process.env, SHARED_RELEASE_LOCK_ROOT: '/var/lib/reno-shared-vps/release-lock-v1' },
    { ...process.env, SHARED_RELEASE_LOCK_ROOT: '/srv/brianstorm/release-lock' },
    { ...process.env, SHARED_RELEASE_LOCK_ROOT: '/var/lib/reno-shared-vps/release.lock' },
    { ...process.env, SHARED_RELEASE_LOCK_ROOT: '/var/lib/reno-shared-vps/release-lock-v1', SHARED_RELEASE_LOCK_PATH: '/tmp/old' },
    { ...process.env, SHARED_RELEASE_LOCK_ROOT: '/var/lib/reno-shared-vps/release-lock-v1', SHARED_RELEASE_LOCK_TEST_MODE: '1' },
  ]) {
    await assert.rejects(execFileAsync('bash', [wrapper, ...base], { env: environment, encoding: 'utf8' }), (error) => error.code === 64);
  }
  await assert.rejects(
    execFileAsync('bash', ['-c', 'exec 9>"$1"; SHARED_RELEASE_LOCK_INHERITED_FD=9 bash "$2" "${@:3}"', '--', join(tmpdir(), 'wrong-release-lock-fd'), wrapper, ...base], { encoding: 'utf8' }),
    (error) => error.code === 64 && /INHERITED_FD is forbidden/.test(error.stderr),
  );
});

test('public wrapper hard-codes the canonical root and privately injects it only after rejecting overrides', async () => {
  const source = await readFile(wrapper, 'utf8');
  assert.match(source, /readonly CANONICAL_LOCK_ROOT='\/var\/lib\/reno-shared-vps\/release-lock-v1'/);
  assert.match(source, /readonly CANONICAL_LOCK_OWNER='root'/);
  assert.match(source, /readonly CANONICAL_LOCK_GROUP='reno-deploy'/);
  assert.match(source, /for forbidden in SHARED_RELEASE_LOCK_ROOT SHARED_RELEASE_LOCK_OWNER SHARED_RELEASE_LOCK_GROUP /);
  assert.match(source, /export SHARED_RELEASE_LOCK_ROOT="\$CANONICAL_LOCK_ROOT"/);
  assert.equal(source.includes('mkdir '), false);
  assert.equal(source.includes('chmod '), false);
  assert.equal(source.includes('chown '), false);
});

test('all lock entrypoints share the exact local-filesystem allowlist', async () => {
  const allowlist = "'ext2/ext3'|ext2|ext3|ext4|xfs|btrfs|tmpfs|overlayfs";
  for (const file of [
    wrapper,
    core,
    resolve('infra/deploy/bootstrap-shared-release-v1.sh'),
  ]) {
    const source = await readFile(file, 'utf8');
    assert.equal(source.includes(allowlist), true, `${file} must use the shared allowlist`);
    assert.equal(source.includes("case \"$filesystem_type\" in 'ext2/ext3'"), file !== core);
    assert.equal(source.includes("case \"$type\" in 'ext2/ext3'"), file === core);
    assert.equal(source.includes('|nfs|'), false, `${file} must not allow NFS`);
  }
});

test('invalid identity inputs are rejected before the transaction can run', async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  await assert.rejects(run(fix, ['--sha', 'short'], ['bash', '-c', 'touch should-not-run']), /40-character lowercase/);
  await assert.rejects(run(fix, ['--run', '0'], ['bash', '-c', 'touch should-not-run']), /positive integer/);
  await assert.rejects(run(fix, ['--ttl-seconds', '0'], ['bash', '-c', 'touch should-not-run']), /positive integer/);
});

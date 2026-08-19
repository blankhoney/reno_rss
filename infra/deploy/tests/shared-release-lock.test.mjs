import assert from 'node:assert/strict';
import { execFile, execFileSync, spawn } from 'node:child_process';
import { mkdtemp, readFile, readdir, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const wrapper = resolve('infra/deploy/with-shared-release-lock.sh');
const sha = 'a'.repeat(40);
const hasLinuxFlock = (() => {
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
  const lockPath = join(directory, 'release.lock');
  return {
    directory,
    lockPath,
    metadata: `${lockPath}.metadata.json`,
    audit: `${lockPath}.audit`,
    environment: { ...process.env, SHARED_RELEASE_LOCK_PATH: lockPath },
    args: (overrides = [], command = ['bash', '-c', 'true']) => [
      '--owner', 'rss', '--repo', 'blankhoney/reno_rss', '--sha', sha,
      '--run', '123', '--ttl-seconds', '30', ...overrides, '--', ...command,
    ],
  };
}

async function run(fix, overrides, command) {
  return execFileAsync('bash', [wrapper, ...fix.args(overrides, command)], {
    env: fix.environment,
    encoding: 'utf8',
  });
}

async function auditEvents(fix) {
  const names = await readdir(fix.audit);
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

function waitForExit(process) {
  return new Promise((resolve) => process.once('exit', (code, signal) => resolve({ code, signal })));
}

flockTest('second owner fails closed while the first transaction holds the live flock', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const first = spawn('bash', [wrapper, ...fix.args([], ['bash', '-c', 'sleep 2'])], { env: fix.environment });
  await waitForFile(fix.metadata);
  await assert.rejects(
    run(fix, ['--owner', 'blog', '--repo', 'blankhoney/reno_blog'], ['bash', '-c', 'exit 99']),
    (error) => error.code === 75 && /another release transaction/.test(error.stderr),
  );
  assert.equal(await new Promise((resolve) => first.once('exit', resolve)), 0);
});

flockTest('a live flock is authoritative even after its diagnostic TTL expires', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const first = spawn('bash', [wrapper, ...fix.args(['--ttl-seconds', '1'], ['bash', '-c', 'sleep 3'])], { env: fix.environment });
  await waitForFile(fix.metadata);
  await new Promise((resolve) => setTimeout(resolve, 1200));
  await assert.rejects(run(fix, [], ['bash', '-c', 'true']), (error) => error.code === 75);
  assert.equal(await new Promise((resolve) => first.once('exit', resolve)), 0);
});

flockTest('only an exact owner and token can remove metadata; mismatch is audited and quarantined', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  await run(fix, [], ['bash', '-c', 'python3 - "$SHARED_RELEASE_LOCK_PATH.metadata.json" <<\'PY\'\nimport json, sys\np = sys.argv[1]\nd = json.load(open(p))\nd["token"] = "0" * 64\nopen(p, "w").write(json.dumps(d))\nPY']);
  assert.equal((await stat(fix.metadata)).isFile(), true);
  const mismatchEvents = await auditEvents(fix);
  assert.equal(mismatchEvents.some((event) => event.event === 'release-refused'), true);

  await run(fix, [], ['bash', '-c', 'true']);
  const events = await auditEvents(fix);
  assert.equal(events.some((event) => event.event === 'quarantined-residual-metadata'), true);
  assert.equal(events.some((event) => event.event === 'released' && event.detail === 'exact-owner-token-match'), true);
});

flockTest('SIGTERM keeps ownership through child termination and leaves an auditable release', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const process = spawn('bash', [wrapper, ...fix.args([], ['bash', '-c', 'sleep 10'])], { env: fix.environment });
  await waitForFile(fix.metadata);
  const exited = waitForExit(process);
  process.kill('SIGTERM');
  const result = await exited;
  assert.deepEqual(result, { code: 128, signal: null });
  const events = await auditEvents(fix);
  assert.equal(events.some((event) => event.event === 'signal' && event.detail === 'TERM'), true);
  assert.equal(events.some((event) => event.event === 'released'), true);
  await assert.rejects(stat(fix.metadata));
});

flockTest('a crashed wrapper cannot release a transaction-held flock; recovery starts only after the child exits', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const process = spawn('bash', [wrapper, ...fix.args([], ['bash', '-c', 'sleep 2'])], { env: fix.environment });
  await waitForFile(fix.metadata);
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
});

flockTest('metadata schema and audit bind the complete v1 identity; source has no force deletion', {}, async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  const captured = `${fix.lockPath}.captured.json`;
  await run(fix, [], ['bash', '-c', 'cp "$SHARED_RELEASE_LOCK_PATH.metadata.json" "$SHARED_RELEASE_LOCK_PATH.captured.json"']);
  const metadata = JSON.parse(await readFile(captured, 'utf8'));
  assert.deepEqual(
    Object.keys(metadata).sort(),
    ['acquiredAt', 'audit', 'contractVersion', 'expiresAt', 'fullSha', 'owner', 'pid', 'repo', 'token', 'workflowRun'].sort(),
  );
  assert.equal(metadata.contractVersion, 1);
  assert.equal(metadata.owner, 'rss');
  assert.equal(metadata.repo, 'blankhoney/reno_rss');
  assert.equal(metadata.fullSha, sha);
  assert.equal(metadata.workflowRun, 123);
  assert.match(metadata.token, /^[0-9a-f]{64}$/);
  const events = await auditEvents(fix);
  const acquired = events.find((event) => event.event === 'acquired');
  assert.deepEqual(
    Object.keys(acquired).sort(),
    ['contractVersion', 'detail', 'event', 'fullSha', 'owner', 'repo', 'timestamp', 'tokenSha256', 'workflowRun'].sort(),
  );
  assert.equal(acquired.contractVersion, 1);
  assert.equal(acquired.fullSha, sha);
  assert.equal(acquired.workflowRun, 123);
  const source = await readFile(wrapper, 'utf8');
  assert.equal(source.includes('rm -f'), false);
  assert.match(source, /if metadata_matches_current_owner; then\n[\s\S]*rm -- "\$METADATA_PATH"/);
});

test('invalid identity inputs are rejected before the transaction can run', async (t) => {
  const fix = await fixture();
  t.after(() => rm(fix.directory, { recursive: true, force: true }));
  await assert.rejects(run(fix, ['--sha', 'short'], ['bash', '-c', 'touch should-not-run']), /40-character lowercase/);
  await assert.rejects(run(fix, ['--run', '0'], ['bash', '-c', 'touch should-not-run']), /positive integer/);
  await assert.rejects(run(fix, ['--ttl-seconds', '0'], ['bash', '-c', 'touch should-not-run']), /positive integer/);
});

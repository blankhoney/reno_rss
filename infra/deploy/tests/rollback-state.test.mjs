import assert from 'node:assert/strict';
import { chmod, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const helper = path.join(repoRoot, 'infra/deploy/rollback-state.sh');
const rollbackFrom = 'a'.repeat(40);
const target = 'b'.repeat(40);
const unknown = 'c'.repeat(40);

async function fixture({ initial = target, activateResult = rollbackFrom, mutateAfterProbe = false } = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'rollback-state-'));
  const state = path.join(root, 'runtime-sha');
  const log = path.join(root, 'calls.log');
  const read = path.join(root, 'read-runtime');
  const activate = path.join(root, 'activate');
  const probe = path.join(root, 'probe');
  await writeFile(state, `${initial}\n`);
  await writeFile(read, `#!/usr/bin/env bash
set -euo pipefail
cat "${state}"
`);
  await writeFile(activate, `#!/usr/bin/env bash
set -euo pipefail
[[ "$#" == 2 ]] || exit 91
printf 'activate %s expected=%s\\n' "$1" "$2" >> "${log}"
printf '%s\\n' '${activateResult}' > "${state}"
`);
  await writeFile(probe, `#!/usr/bin/env bash
set -euo pipefail
[[ "$#" == 4 ]] || exit 92
printf 'probe phase=%s runtime=%s rollbackFrom=%s target=%s\\n' "$1" "$2" "$3" "$4" >> "${log}"
${mutateAfterProbe ? `printf '%s\\n' '${target}' > "${state}"` : ''}
`);
  await Promise.all([read, activate, probe].map((file) => chmod(file, 0o755)));
  return {
    root,
    log,
    run() {
      return spawnSync('bash', ['-c', `set -euo pipefail
source "$1"
rollback_state_compensate "$2" "$3" "$4" "$5" "$6"
`, 'rollback-state-test', helper, rollbackFrom, target, read, activate, probe], {
        cwd: repoRoot,
        encoding: 'utf8',
      });
    },
    async calls() {
      try { return (await readFile(log, 'utf8')).trim().split('\n').filter(Boolean); }
      catch { return []; }
    },
    async cleanup() { await rm(root, { recursive: true, force: true }); },
  };
}

test('compensation reads rollbackFrom and emits only an actual-runtime post-compensation receipt input', async () => {
  const item = await fixture({ initial: rollbackFrom });
  try {
    const result = item.run();
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout.trim(), 'already-rolled-back');
    assert.deepEqual(await item.calls(), [
      `probe phase=post-compensation runtime=${rollbackFrom} rollbackFrom=${rollbackFrom} target=${target}`,
    ]);
  } finally { await item.cleanup(); }
});

test('compensation activates rollbackFrom only when the actual runtime is the failed target', async () => {
  const item = await fixture({ initial: target, activateResult: rollbackFrom });
  try {
    const result = item.run();
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout.trim(), 'rollback-required');
    assert.deepEqual(await item.calls(), [
      `activate ${rollbackFrom} expected=${target}`,
      `probe phase=post-compensation runtime=${rollbackFrom} rollbackFrom=${rollbackFrom} target=${target}`,
    ]);
  } finally { await item.cleanup(); }
});

test('unknown current runtime fails closed without activation or a receipt input', async () => {
  const item = await fixture({ initial: unknown });
  try {
    const result = item.run();
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /refusing compensation: current runtime/);
    assert.deepEqual(await item.calls(), []);
  } finally { await item.cleanup(); }
});

test('race guard rejects an activation that does not restore rollbackFrom before probing', async () => {
  const item = await fixture({ initial: target, activateResult: target });
  try {
    const result = item.run();
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /did not restore rollbackFrom/);
    assert.deepEqual(await item.calls(), [`activate ${rollbackFrom} expected=${target}`]);
  } finally { await item.cleanup(); }
});

test('race guard rejects a runtime change after the post-compensation probe', async () => {
  const item = await fixture({ initial: rollbackFrom, mutateAfterProbe: true });
  try {
    const result = item.run();
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /runtime changed during compensation/);
    assert.deepEqual(await item.calls(), [
      `probe phase=post-compensation runtime=${rollbackFrom} rollbackFrom=${rollbackFrom} target=${target}`,
    ]);
  } finally { await item.cleanup(); }
});

test('decision validates full SHA inputs and never treats malformed state as a rollout target', () => {
  const result = spawnSync('bash', ['-c', `
source "$1"
rollback_state_decide "$2" "$3" short
`, 'rollback-state-test', helper, rollbackFrom, target], { cwd: repoRoot, encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /current runtime SHA must be a full 40-character lowercase commit SHA/);
});

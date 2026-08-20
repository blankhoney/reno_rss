import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const validator = path.join(repoRoot, '.github/scripts/validate-known-hosts.sh');
const placeholderKey = 'AAAAC3NzaC1lZDI1NTE5AAAAICAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';

async function run({ host = 'vps.example.test', port = '22', entries = [] } = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'known-hosts-contract-'));
  const knownHosts = path.join(root, 'known_hosts');
  await writeFile(
    knownHosts,
    `${entries.map((entry) => `${entry} ssh-ed25519 ${placeholderKey}`).join('\n')}\n`,
    { mode: 0o600 },
  );
  const result = spawnSync('bash', [validator], {
    cwd: repoRoot,
    env: {
      ...process.env,
      VPS_HOST: host,
      VPS_PORT: port,
      VPS_KNOWN_HOSTS_FILE: knownHosts,
    },
    encoding: 'utf8',
  });
  await rm(root, { recursive: true, force: true });
  return result;
}

test('accepts only the exact OpenSSH host token for the actual port', async () => {
  assert.equal((await run({ entries: ['vps.example.test'] })).status, 0);
  assert.equal((await run({ port: '2222', entries: ['[vps.example.test]:2222'] })).status, 0);
  assert.notEqual((await run({ port: '2222', entries: ['vps.example.test'] })).status, 0);
  assert.notEqual((await run({ port: '2222', entries: ['[vps.example.test]:22'] })).status, 0);
});

test('fails closed on invalid identity, port, empty file, or symlinked known_hosts', async () => {
  for (const options of [
    { host: 'user@vps.example.test', entries: ['vps.example.test'] },
    { host: '-oProxyCommand=bad', entries: ['vps.example.test'] },
    { port: '0', entries: ['vps.example.test'] },
    { port: '70000', entries: ['vps.example.test'] },
    { entries: [] },
  ]) {
    assert.notEqual((await run(options)).status, 0);
  }

  const root = await mkdtemp(path.join(os.tmpdir(), 'known-hosts-symlink-'));
  try {
    const target = path.join(root, 'target');
    const link = path.join(root, 'known_hosts');
    await writeFile(target, `vps.example.test ssh-ed25519 ${placeholderKey}\n`, { mode: 0o600 });
    await symlink(target, link);
    const result = spawnSync('bash', [validator], {
      cwd: repoRoot,
      env: {
        ...process.env,
        VPS_HOST: 'vps.example.test',
        VPS_PORT: '22',
        VPS_KNOWN_HOSTS_FILE: link,
      },
      encoding: 'utf8',
    });
    assert.notEqual(result.status, 0);
  } finally { await rm(root, { recursive: true, force: true }); }

  const source = await readFile(validator, 'utf8');
  assert.equal(source.includes('ssh-keyscan'), false);
  assert.ok(
    source.indexOf("stat -c '%a'") < source.indexOf("stat -f '%Lp'"),
    'Linux must use GNU stat directly instead of treating GNU stat -f output as a BSD mode',
  );
});

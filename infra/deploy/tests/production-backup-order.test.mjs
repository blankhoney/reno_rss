import assert from 'node:assert/strict';
import { chmod, mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const deployScript = path.join(repoRoot, 'infra/scripts/deploy.sh');
const backupScript = path.join(repoRoot, 'infra/scripts/backup.sh');
const remoteTransaction = path.join(repoRoot, '.github/scripts/remote-deploy.sh');
const ciWorkflow = path.join(repoRoot, '.github/workflows/ci.yml');

test('canonical CI executes the production backup ordering gate', async () => {
  const ci = await readFile(ciWorkflow, 'utf8');
  assert.match(ci, /infra\/deploy\/tests\/production-backup-order\.test\.mjs/);
});

function firstAfter(source, needle, offset) {
  const index = source.indexOf(needle, offset);
  assert.notEqual(index, -1, `missing deployment mutation: ${needle}`);
  return index;
}

test('production backup completes before any deployment mutation can start a revision', async () => {
  const source = await readFile(deployScript, 'utf8');
  const backupMarker = source.indexOf('# PROD_MIGRATION_BACKUP_GATE');
  const backupGate = source.indexOf('\nrun_prod_migration_backup', backupMarker);
  assert.ok(backupMarker >= 0 && backupGate > backupMarker, 'production backup gate must remain explicit');

  for (const mutation of [
    'docker network create myrss-app',
    'up -d --remove-orphans',
    '"${BACKEND_COMPOSE[@]}" pull reader-web ai-reader-api ai-reader-worker',
    '"${BACKEND_COMPOSE[@]}" up -d --no-build --remove-orphans',
    '"${BACKEND_COMPOSE[@]}" up -d --build --remove-orphans',
    'exec -T ai-reader-api alembic upgrade head',
    'up -d --force-recreate --no-deps authelia',
  ]) {
    assert.ok(firstAfter(source, mutation, backupGate) > backupGate, `${mutation} must follow backup`);
  }
});

test('trusted remote transaction verifies production backup before shared mutations', async () => {
  const source = await readFile(remoteTransaction, 'utf8');
  const transaction = source.indexOf('locked_mutation(){');
  const prepare = firstAfter(source, 'prepare_control_plane||return', transaction);
  const backup = firstAfter(source, 'run_production_prebackup||return', prepare);
  assert.ok(prepare < backup);
  for (const mutation of [
    'ensure_shared_edge||return',
    'docker login ghcr.io',
    'verify_image "$web_image"',
    'release_and_verify',
  ]) {
    assert.ok(firstAfter(source, mutation, backup) > backup, `${mutation} must follow backup`);
  }
});

test('the production backup gate remains fail-closed while staging is explicitly a no-op', async () => {
  const source = await readFile(deployScript, 'utf8');
  const functionStart = source.indexOf('run_prod_migration_backup() {');
  const functionEnd = source.indexOf('\n}\n\n# Alembic must run only', functionStart);
  assert.ok(functionStart >= 0 && functionEnd > functionStart);
  const backup = source.slice(functionStart, functionEnd);

  assert.match(backup, /if \[\[ "\$ENV" != "prod" \]\]; then[\s\S]*return/);
  assert.match(backup, /TRUSTED_PRODUCTION_BACKUP_EVIDENCE/);
  assert.match(backup, /trusted-production-backup\/v1/);
  assert.match(backup, /sha256sum -c/);
  assert.doesNotMatch(backup, /backup\.sh/);
  assert.match(backup, /exit 1/);
});

test('missing trusted production backup evidence starts no Compose revision', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'production-backup-order-'));
  const scripts = path.join(root, 'infra/scripts');
  const bin = path.join(root, 'bin');
  const dockerLog = path.join(root, 'docker.log');
  try {
    await mkdir(scripts, { recursive: true });
    await mkdir(bin);
    await writeFile(path.join(root, '.env'), '\n');
    await writeFile(path.join(scripts, 'deploy.sh'), await readFile(deployScript));
    await writeFile(dockerLog, '');
    await writeFile(path.join(bin, 'docker'), `#!/usr/bin/env bash
printf 'docker %s\\n' "$*" >> "${dockerLog}"
exit 99
`, { mode: 0o755 });
    await Promise.all([
      chmod(path.join(scripts, 'deploy.sh'), 0o755),
      chmod(path.join(bin, 'docker'), 0o755),
    ]);

    const result = spawnSync('bash', [path.join(scripts, 'deploy.sh'), 'prod', 'sha-test'], {
      cwd: root,
      env: { ...process.env, PATH: `${bin}:${process.env.PATH}` },
      encoding: 'utf8',
    });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /requires safe trusted backup evidence/);
    assert.equal(await readFile(dockerLog, 'utf8'), '');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('backup directories are exclusive even when two backups start in the same second', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'production-backup-unique-'));
  const bin = path.join(root, 'bin');
  try {
    await mkdir(bin);
    await writeFile(path.join(bin, 'date'), '#!/usr/bin/env bash\nprintf "2026-08-20_12-00-00\\n"\n', { mode: 0o755 });
    await writeFile(path.join(bin, 'docker'), '#!/usr/bin/env bash\nprintf "fixture dump\\n"\n', { mode: 0o755 });
    await Promise.all([chmod(path.join(bin, 'date'), 0o755), chmod(path.join(bin, 'docker'), 0o755)]);
    const outputs = [];
    for (let index = 0; index < 2; index += 1) {
      const result = spawnSync('bash', [backupScript], {
        cwd: root, env: { ...process.env, PATH: `${bin}:${process.env.PATH}` }, encoding: 'utf8',
      });
      assert.equal(result.status, 0, result.stderr);
      outputs.push(result.stdout.match(/^BACKUP_DIR=(.+)$/m)?.[1]);
    }
    assert.equal(new Set(outputs).size, 2);
    assert.ok(outputs.every((value) => value?.includes('2026-08-20_12-00-00.')));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('Linux deploy gate revalidates one bound backup and rejects later tampering', { skip: os.platform() !== 'linux' }, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'production-backup-evidence-'));
  try {
    const backupDir = path.join(root, 'backup', 'fixture');
    await mkdir(backupDir, { recursive: true });
    const dump = path.join(backupDir, 'scoring.dump');
    const checksums = path.join(backupDir, 'checksums.txt');
    const evidence = path.join(root, 'evidence.json');
    const operation = 'a'.repeat(40);
    const payload = 'verified backup\n';
    const digest = createHash('sha256').update(payload).digest('hex');
    await writeFile(dump, payload);
    await writeFile(checksums, `${digest}  ${dump}\n`);
    const checksumDigest = createHash('sha256').update(await readFile(checksums)).digest('hex');
    await writeFile(evidence, `${JSON.stringify({
      contractVersion: 'trusted-production-backup/v1', workflowOperationSha: operation,
      environment: 'prod', backupDir, checksumFile: checksums,
      checksumDigest: `sha256:${checksumDigest}`,
    })}\n`, { mode: 0o600 });
    await chmod(evidence, 0o600);

    const source = await readFile(deployScript, 'utf8');
    const start = source.indexOf('run_prod_migration_backup() {');
    const end = source.indexOf('\n}\n\n# Alembic must run only', start) + 2;
    const harness = `set -euo pipefail\nENV=prod\nREPO_ROOT="$1"\n${source.slice(start, end)}\nrun_prod_migration_backup\n`;
    const env = {
      ...process.env,
      TRUSTED_PRODUCTION_BACKUP_EVIDENCE: evidence,
      TRUSTED_DEPLOY_OPERATION_SHA: operation,
    };
    const accepted = spawnSync('bash', ['-c', harness, 'gate', root], { env, encoding: 'utf8' });
    assert.equal(accepted.status, 0, accepted.stderr);

    await writeFile(dump, 'tampered after evidence\n');
    const rejected = spawnSync('bash', ['-c', harness, 'gate', root], { env, encoding: 'utf8' });
    assert.notEqual(rejected.status, 0);
    assert.match(rejected.stdout, /备份校验失败/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

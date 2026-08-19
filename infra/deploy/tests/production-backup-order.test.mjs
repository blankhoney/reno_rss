import assert from 'node:assert/strict';
import { chmod, mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const deployScript = path.join(repoRoot, 'infra/scripts/deploy.sh');
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
  assert.match(backup, /"\$SCRIPT_DIR\/backup\.sh" prod/);
  assert.match(backup, /停止迁移和部署/);
  assert.match(backup, /exit 1/);
});

test('a failed production backup starts no Compose revision', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'production-backup-order-'));
  const scripts = path.join(root, 'infra/scripts');
  const bin = path.join(root, 'bin');
  const dockerLog = path.join(root, 'docker.log');
  try {
    await mkdir(scripts, { recursive: true });
    await mkdir(bin);
    await writeFile(path.join(root, '.env'), '\n');
    await writeFile(path.join(scripts, 'deploy.sh'), await readFile(deployScript));
    await writeFile(path.join(scripts, 'backup.sh'), `#!/usr/bin/env bash
printf 'backup %s\\n' "$*" >> "${dockerLog}"
exit 47
`, { mode: 0o755 });
    await writeFile(path.join(bin, 'docker'), `#!/usr/bin/env bash
printf 'docker %s\\n' "$*" >> "${dockerLog}"
exit 99
`, { mode: 0o755 });
    await Promise.all([
      chmod(path.join(scripts, 'deploy.sh'), 0o755),
      chmod(path.join(scripts, 'backup.sh'), 0o755),
      chmod(path.join(bin, 'docker'), 0o755),
    ]);

    const result = spawnSync('bash', [path.join(scripts, 'deploy.sh'), 'prod', 'sha-test'], {
      cwd: root,
      env: { ...process.env, PATH: `${bin}:${process.env.PATH}` },
      encoding: 'utf8',
    });

    assert.notEqual(result.status, 0);
    assert.match(result.stdout, /prod 数据库备份失败，停止迁移和部署/);
    assert.equal(await readFile(dockerLog, 'utf8'), 'backup prod\n');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

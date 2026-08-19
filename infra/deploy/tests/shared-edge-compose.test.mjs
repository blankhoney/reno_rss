import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const composePath = 'infra/compose/docker-compose.edge.yml';

test('edge compose declares both shared production networks without duplicate mounts', async () => {
  const result = spawnSync('docker', [
    'compose',
    '--env-file', '.env.example',
    '-f', composePath,
    'config',
    '--format', 'json',
  ], { cwd: repoRoot, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const config = JSON.parse(result.stdout);
  const caddy = config.services.caddy;
  assert.deepEqual(Object.keys(caddy.networks).sort(), ['app', 'brianstorm_edge']);
  assert.equal(config.networks.app.name, 'myrss-app');
  assert.equal(config.networks.brianstorm_edge.name, 'brianstorm-edge');
  assert.equal(config.networks.brianstorm_edge.external, true);
  const targets = caddy.volumes.map((volume) => volume.target);
  assert.equal(new Set(targets).size, targets.length);
});

test('RSS deployment restores shared membership after compose activation and before Caddy reload', async () => {
  const source = await readFile(path.join(repoRoot, 'infra/scripts/deploy.sh'), 'utf8');
  const edgeStart = source.indexOf('-f "$REPO_ROOT/infra/compose/docker-compose.edge.yml" \\\n    up -d --remove-orphans');
  const restore = source.indexOf('bash "$REPO_ROOT/infra/deploy/ensure-shared-edge.sh"');
  const validate = source.indexOf('exec -T caddy caddy validate');
  const reload = source.indexOf('exec -T caddy caddy reload');
  assert.notEqual(edgeStart, -1, 'edge activation must not unconditionally force-recreate shared Caddy');
  assert.ok(edgeStart < restore, 'edge recovery must follow any compose activation');
  assert.ok(restore < validate && validate < reload, 'recovery must precede validate/reload');
});

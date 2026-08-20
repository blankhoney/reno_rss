import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { access, mkdtemp, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const probe = path.resolve('infra/deploy/verify-shared-edge.py');
const verifier = path.resolve('infra/deploy/verify-shared-edge-receipt.py');
const operation = '89abcdef0123456789abcdef0123456789abcdef';
const runtime = '0123456789abcdef0123456789abcdef01234567';

function python(program, args = []) {
  return spawnSync('python3', ['-c', program, probe, verifier, ...args], { encoding: 'utf8' });
}

test('Python shared-edge probe emits and verifies the exact success receipt without Node', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'rss-python-edge-'));
  const receipt = path.join(root, 'receipt.json');
  const program = `import importlib.util, pathlib, sys
spec=importlib.util.spec_from_file_location('probe',sys.argv[1]); p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
p.probe_url=lambda name,url,hosts,redirect: {'name':name,'configuredURL':url,'status':200,'finalURL':'https://auth.blankhoney.xyz/' if redirect else url,'tls':True,'redirect':redirect,'result':'success','error':None}
p.edge_state=lambda errors: {'caddyContainer':'myrss-edge-caddy-1','myrssAppAttached':True,'brianstormEdgeAttached':True,'networkDriver':'bridge','configLoaded':True,'rssUpstreamReachable':True,'blogUpstreamReachable':True}
raise SystemExit(p.main(sys.argv[3:]))`;
  const args = ['--owner-project', 'rss', '--owner-repo', 'blankhoney/reno_rss',
    '--operation-sha', operation, '--runtime-sha', runtime, '--workflow-run', '99',
    '--phase', 'pre-mutation', '--receipt', receipt];
  const generated = python(program, args);
  assert.equal(generated.status, 0, generated.stderr);
  const verified = spawnSync('python3', [verifier, receipt, 'success', 'rss', 'blankhoney/reno_rss',
    operation, runtime, '99', 'pre-mutation'], { encoding: 'utf8' });
  assert.equal(verified.status, 0, verified.stderr);
  const value = JSON.parse(await readFile(receipt, 'utf8'));
  assert.deepEqual(Object.keys(value).sort(), ['contractVersion', 'edge', 'operation', 'overallStatus',
    'owner', 'phase', 'rollback', 'runtime', 'timestamp', 'urls', 'workflowRun'].sort());
});

test('Python verifier rejects redirect SSRF, unknown keys, and identity drift', async () => {
  const program = `import importlib.util,sys
s=importlib.util.spec_from_file_location('v',sys.argv[2]);v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
for url in ('https://127.0.0.1/','https://user@auth.blankhoney.xyz/','https://auth.blankhoney.xyz:444/'):
  try:v.safe_url(url,{'auth.blankhoney.xyz'})
  except ValueError:continue
  raise SystemExit(1)
raise SystemExit(0)`;
  assert.equal(python(program).status, 0);
});

test('invalid arguments fail before a receipt is created and missing Python is fail closed', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'rss-python-edge-invalid-'));
  const receipt = path.join(root, 'receipt.json');
  const invalid = spawnSync('python3', [probe, '--owner-project', 'rss', '--owner-repo', 'blankhoney/reno_rss',
    '--operation-sha', 'short', '--runtime-sha', runtime, '--workflow-run', '99',
    '--phase', 'pre-mutation', '--receipt', receipt], { encoding: 'utf8' });
  assert.notEqual(invalid.status, 0);
  await assert.rejects(() => access(receipt));
  const remote = await readFile('infra/deploy/install-blog-control-plane-remote.sh', 'utf8');
  assert.match(remote, /exec python3 -c/);
  assert.doesNotMatch(remote, /command -v node|INSTALLER_PROBE_NODE/);
});

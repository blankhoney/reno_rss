import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  blogInstallerContract,
  verifyBlogInstallerInputs,
} from '../verify-blog-control-plane-installer-inputs.mjs';

const workflow = readFileSync('.github/workflows/install-blog-control-plane.yml', 'utf8');

test('root-capable installer pins the reviewed Blog control plane and frozen artifact', () => {
  assert.match(workflow, /ref: 48a12b8cfd4c33a20d0d9ded922e5c8616a4b803/);
  assert.match(workflow, /CONTROL_PLANE_CI_RUN: '32351611647'/);
  assert.match(workflow, /OPERATION_SHA: e52ab44f8fb963a8f4d7cd1da326092f7972b2a8/);
  assert.match(workflow, /PRODUCER_RUN: '32339806061'/);
  assert.match(workflow, /ARTIFACT_ID: '9396499072'/);
  assert.match(workflow, /ARTIFACT_DIGEST: sha256:d5929e143256f83d9c2cb0d7254d1f1181e02045ac43916795857913aabd8378/);
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
  assert.match(workflow, /install-trusted-blog-transaction-remote\.sh/);
  assert.match(workflow, /verify-trusted-blog-install-receipt\.mjs/);
  assert.match(workflow, /blog-trusted-installer-\$\{\{ github\.run_id \}\}/);
  assert.doesNotMatch(workflow, /ssh-keyscan|StrictHostKeyChecking=no/);
  assert.doesNotMatch(workflow, /docker (?:compose )?build|release\.tar\.gz/);
});

test('identity drift fails before trusted SSH or remote mutation', () => {
  const identity = workflow.indexOf('Authenticate the Blog control plane and frozen artifact');
  const ssh = workflow.indexOf('Set up trusted SSH');
  const install = workflow.indexOf('Install Blog control plane under the canonical lock');
  assert.ok(identity > 0 && identity < ssh && ssh < install);
  assert.match(workflow, /verify-blog-control-plane-installer-inputs\.mjs/);
});

function fixtures() {
  const { repository, controlPlane, operation } = blogInstallerContract;
  const run = (identity) => ({
    id: identity.workflowRun,
    run_attempt: identity.workflowRunAttempt,
    name: 'ci', event: 'push', status: 'completed', conclusion: 'success', head_branch: 'main',
    head_repository: { full_name: repository }, head_sha: identity.fullSha,
  });
  return {
    control: run(controlPlane),
    producer: run(operation),
    artifact: {
      id: operation.artifactId, expired: false, name: operation.artifactName,
      digest: operation.artifactDigest,
      workflow_run: { id: operation.workflowRun, head_branch: 'main', head_sha: operation.fullSha },
    },
  };
}

test('metadata verifier accepts only the exact current control plane and frozen artifact', () => {
  const valid = fixtures();
  assert.doesNotThrow(() => verifyBlogInstallerInputs(valid.control, valid.producer, valid.artifact));
  for (const mutate of [
    (value) => { value.control.head_sha = '0'.repeat(40); },
    (value) => { value.control.run_attempt = 2; },
    (value) => { value.producer.id += 1; },
    (value) => { value.artifact.expired = true; },
    (value) => { value.artifact.digest = `sha256:${'0'.repeat(64)}`; },
    (value) => { value.artifact.workflow_run.head_sha = '0'.repeat(40); },
  ]) {
    const value = structuredClone(valid);
    mutate(value);
    assert.throws(
      () => verifyBlogInstallerInputs(value.control, value.producer, value.artifact),
      /identity contract mismatch/,
    );
  }
});

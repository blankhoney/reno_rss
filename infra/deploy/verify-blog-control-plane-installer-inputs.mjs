#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

export const blogInstallerContract = Object.freeze({
  repository: 'blankhoney/my_blog',
  repositoryId: 1236581850,
  workflowId: 275301410,
  runtime: Object.freeze({
    fullSha: '1667b3c891958c65426d9f3ed7dd0426f012cefc',
    releaseId: '20260719-201357-1667b3c',
  }),
  controlPlane: Object.freeze({
    fullSha: '48a12b8cfd4c33a20d0d9ded922e5c8616a4b803',
    workflowRun: 32351611647,
    workflowRunAttempt: 1,
  }),
  operation: Object.freeze({
    fullSha: 'e52ab44f8fb963a8f4d7cd1da326092f7972b2a8',
    workflowRun: 32339806061,
    workflowRunAttempt: 1,
    artifactId: 9396499072,
    artifactName: 'brianstorm-production-32339806061',
    artifactDigest: 'sha256:d5929e143256f83d9c2cb0d7254d1f1181e02045ac43916795857913aabd8378',
  }),
});

function validRun(run, expected) {
  return run?.id === expected.workflowRun &&
    run?.run_attempt === expected.workflowRunAttempt &&
    run?.name === 'ci' && run?.event === 'push' && run?.status === 'completed' &&
    run?.conclusion === 'success' && run?.head_branch === 'main' &&
    run?.workflow_id === blogInstallerContract.workflowId &&
    run?.path === '.github/workflows/ci.yml' &&
    run?.repository?.id === blogInstallerContract.repositoryId &&
    run?.repository?.full_name === blogInstallerContract.repository &&
    run?.head_repository?.id === blogInstallerContract.repositoryId &&
    run?.head_repository?.full_name === blogInstallerContract.repository &&
    run?.head_sha === expected.fullSha;
}

export function verifyBlogInstallerInputs(controlRun, producerRun, artifact, runtimeCommit) {
  const { controlPlane, operation } = blogInstallerContract;
  if (!validRun(controlRun, controlPlane) || !validRun(producerRun, operation) ||
      artifact?.id !== operation.artifactId || artifact?.expired !== false ||
      artifact?.name !== operation.artifactName || artifact?.digest !== operation.artifactDigest ||
      artifact?.workflow_run?.id !== operation.workflowRun ||
      artifact?.workflow_run?.head_branch !== 'main' ||
      artifact?.workflow_run?.head_sha !== operation.fullSha ||
      runtimeCommit?.sha !== blogInstallerContract.runtime.fullSha ||
      runtimeCommit?.html_url !== `https://github.com/${blogInstallerContract.repository}/commit/${blogInstallerContract.runtime.fullSha}`) {
    throw new Error('Blog control-plane installer identity contract mismatch');
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv.length !== 6) {
    console.error('usage: verify-blog-control-plane-installer-inputs.mjs <control-run.json> <producer-run.json> <artifact.json> <runtime-commit.json>');
    process.exit(64);
  }
  try {
    const [controlPath, producerPath, artifactPath, runtimePath] = process.argv.slice(2);
    verifyBlogInstallerInputs(
      JSON.parse(readFileSync(controlPath, 'utf8')),
      JSON.parse(readFileSync(producerPath, 'utf8')),
      JSON.parse(readFileSync(artifactPath, 'utf8')),
      JSON.parse(readFileSync(runtimePath, 'utf8')),
    );
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}

# CI/CD Specification

[English](SPEC-CICD.md) | [中文](SPEC-CICD.zh-CN.md)

## Background

Reno RSS / AI Reader has GitHub Actions checks, GHCR image publishing, remote VPS deployment scripts, and smoke tests. The current `ci.yml` runs checks for pull request events; only a `push` to `refs/heads/main` tests, builds, publishes, enters the staging deploy path, and runs smoke checks. That staging path fails closed when `VPS_KNOWN_HOSTS` is unavailable, and the remote path stops when the VPS repository has tracked local changes.

This specification records that current delivery contract and the evidence required to keep it working.

## Goals

- Deploy staging only after a successful `push` to `refs/heads/main`; pull request events run checks only.
- Keep production deploy requests manual; a later trusted orchestrator owns GitHub Environment approval and secret-bearing execution.
- Build application images in GitHub Actions and pull them on the VPS from GHCR.
- Keep runtime secrets on the VPS or in GitHub Secrets; never print them in logs.
- Make failures easy to classify as checks, image build, SSH/secret, VPS dirty worktree, deploy, or smoke-test failures.

## Non-Goals

- No Kubernetes, self-hosted runner, or new deployment platform.
- No automatic production deploy from `main`.
- No Git history rewrite or server secret migration in the CI workflow.
- No MiniMax cost-incurring E2E checks in automated smoke tests.

## User Stories

- As the maintainer, when I push to `main`, staging should update automatically after checks pass.
- As the maintainer, I should not SSH into the VPS for normal staging deploys.
- As a visitor, the staging app should continue to provide the shared-user functional demo while keeping admin operations role-protected.
- As the maintainer, production should only change after a manual GitHub deployment approval.

## Functional Requirements

- `ci.yml` must run Python tests/lint, reader-web tests/build, Compose validation, and explicit Trivy high/critical vulnerability plus secret scanning.
- `ci.yml` must build and push `ai-reader-web`, `ai-reader-api`, and `ai-reader-worker` images to GHCR with `sha-<short_sha>` tags.
- Pull request events run checks only. Only a `push` to `refs/heads/main` enters the staging deploy path after images are published; that path still fails closed when `VPS_KNOWN_HOSTS` is unavailable.
- Fork PRs must not deploy and must not read deployment secrets.
- `deploy-staging.yml` remains a manual request entry by explicit immutable image tag and full deploy SHA.
- `deploy-prod.yml` remains a manual request entry; the trusted orchestrator must apply the `production` environment approval before deployment.
- `rollback.yml` remains a manual rollback request entry by explicit immutable image tag and full deploy SHA.
- Remote deploy must stop if the VPS tracked worktree is dirty.
- Staging smoke tests must verify containers, health endpoints, the public AI Reader workbench, anonymous articles `200`, and anonymous Admin `403` with non-mutating checks. They must not invoke actions that mark articles read, fetch content, sync, score, ask an agent, or mutate business data.

## Non-Functional Requirements

- **Security**: secrets, cookies, SSH keys, API keys, and Basic Auth headers must not be printed.
- **Traceability**: request artifacts must include the full deploy SHA and immutable image tag; the trusted orchestrator records images, target URL, and smoke-test success after execution.
- **Idempotence**: rerunning a deploy for the same image tag should converge services without manual cleanup.
- **Environment isolation**: staging automation must not deploy production.
- **Cost control**: automated smoke tests must not trigger LLM scoring or Agent calls.

## Interfaces and Boundaries

- **GitHub Actions**: `ci.yml` is the normal path; `deploy-staging.yml`, `deploy-prod.yml`, and `rollback.yml` are manual request paths. GitHub loads each workflow YAML from the user-selected dispatch ref, but the request job does not checkout or execute target repository code or access deployment secrets. `trusted-deploy.yml` is currently verify-only: it checks completed request-run/artifact/repository/ref/SHA and canonical `ci.yml` publication provenance from the default main checkout, then stops without an environment, secret, SSH, or deploy step. Its workflow-ID allowlist is intentionally unregistered until maintainer control-plane evidence exists, so it fails closed. A later execution phase must preserve this provenance gate before reading deployment secrets.
- **Request artifact**: each manual request uploads one fixed JSON artifact with exactly `schema_version`, `request_type`, `environment`, `image_tag`, and `deploy_sha`. `schema_version` is `trusted-deploy-request/v1`; `image_tag` must be `sha-<7 lowercase hex>` and match the first seven characters of the full lowercase 40-character `deploy_sha`. Fixed artifact names are `trusted-staging-deploy-request`, `trusted-production-deploy-request`, and `trusted-rollback-request`.
- **Rollback provenance boundary**: `trusted-deploy.yml` now verifies the rollback request run, fixed artifact, canonical repository/main provenance, and successful canonical `ci.yml` publication for the target SHA, but it remains verify-only and cannot select an environment or deploy. The remote contract is fixed to `refs/heads/main` and accepts a target SHA only after it exists and is an ancestor of the fetched main tip (`.github/scripts/remote-deploy.sh:39-42,108-138`). Do not restore arbitrary `git_ref` input or the retired `FETCH_HEAD^{commit} == DEPLOY_SHA` equality as an execution contract.
- **Trusted orchestrator boundary**: a later trusted workflow consumes the request artifact as data, applies environment approval and secrets, and may reuse the already-verified remote deploy path.
- **Remote deploy**: `.github/scripts/remote-deploy.sh` remains the trusted execution path for a later orchestrator. It SSHs to `VPS_APP_DIR`, verifies a clean tracked worktree, checks out `DEPLOY_SHA`, logs in to GHCR, and runs `infra/scripts/deploy.sh`.
- **Smoke test**: `infra/scripts/smoke-test.sh` validates runtime health without exposing secrets or mutating business data.
- **VPS runtime state**: `.env`, Authelia users, and other runtime secrets stay outside Git.

## Acceptance Criteria

- A `main` push produces a `ci` workflow where `deploy staging` runs instead of being skipped.
- The workflow publishes all three GHCR images with the expected `sha-<short_sha>` tag.
- The staging deploy job completes remote deploy and smoke test successfully.
- `https://staging-ai-reader.blankhoney.xyz/` and `/?module=all&sort=default&lang=zh` render the public functional demo.
- An anonymous `GET /api/articles` returns `200`, while an anonymous Admin request returns `403`.
- Production remains unchanged unless a trusted orchestrator consumes a manually created `deploy-prod.yml` request and applies the `production` approval gate.

## Operational Blocker Handling

If remote deploy reports a dirty tracked worktree on the VPS, do not reset automatically. Diagnose the dirty file first:

- temporary server edit: restore the repository version after human confirmation
- required runtime setting: migrate it to `.env` or an ignored runtime file
- uncertain change: stop and report the diff without printing secrets

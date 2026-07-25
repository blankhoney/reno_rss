# CI/CD Specification

[English](SPEC-CICD.md) | [中文](SPEC-CICD.zh-CN.md)

## Background

Reno RSS / AI Reader has GitHub Actions checks, GHCR image publishing, remote VPS deployment scripts, and smoke tests. The current `ci.yml` tests, builds, publishes, deploys staging, and runs smoke checks for same-repository pull requests and `main` pushes. The remote path stops when the VPS repository has tracked local changes.

This specification records that current delivery contract and the evidence required to keep it working.

## Goals

- Automatically deploy staging after a successful same-repository PR update or `main` push.
- Keep production deploys manual and protected by the GitHub `production` environment.
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
- Same-repository PRs and `main` pushes must deploy staging after images are published.
- Fork PRs must not deploy and must not read deployment secrets.
- `deploy-staging.yml` remains as a manual fallback by explicit image tag.
- `deploy-prod.yml` remains manual and must use the `production` environment.
- `rollback.yml` continues to deploy a previous image tag through the same remote deploy path.
- Remote deploy must stop if the VPS tracked worktree is dirty.
- Staging smoke tests must verify containers, health endpoints, the public AI Reader workbench, anonymous articles `200`, and anonymous Admin `403` with non-mutating checks. They must not invoke actions that mark articles read, fetch content, sync, score, ask an agent, or mutate business data.

## Non-Functional Requirements

- **Security**: secrets, cookies, SSH keys, API keys, and Basic Auth headers must not be printed.
- **Traceability**: workflow summaries must include commit SHA, image tag, images, staging URL, and smoke-test success.
- **Idempotence**: rerunning a deploy for the same image tag should converge services without manual cleanup.
- **Environment isolation**: staging automation must not deploy production.
- **Cost control**: automated smoke tests must not trigger LLM scoring or Agent calls.

## Interfaces and Boundaries

- **GitHub Actions**: `ci.yml` is the normal path; `deploy-staging.yml`, `deploy-prod.yml`, and `rollback.yml` are manual control paths.
- **Image tags**: the deploy image tag is `sha-<short_sha>` and must match the code revision being deployed.
- **Remote deploy**: `.github/scripts/remote-deploy.sh` SSHs to `VPS_APP_DIR`, verifies a clean tracked worktree, checks out `DEPLOY_SHA`, logs in to GHCR, and runs `infra/scripts/deploy.sh`.
- **Smoke test**: `infra/scripts/smoke-test.sh` validates runtime health without exposing secrets or mutating business data.
- **VPS runtime state**: `.env`, Authelia users, and other runtime secrets stay outside Git.

## Acceptance Criteria

- A `main` push produces a `ci` workflow where `deploy staging` runs instead of being skipped.
- The workflow publishes all three GHCR images with the expected `sha-<short_sha>` tag.
- The staging deploy job completes remote deploy and smoke test successfully.
- `https://staging-ai-reader.blankhoney.xyz/` and `/?module=all&sort=default&lang=zh` render the public functional demo.
- An anonymous `GET /api/articles` returns `200`, while an anonymous Admin request returns `403`.
- Production remains unchanged unless `deploy-prod.yml` is manually run and approved.

## Operational Blocker Handling

If remote deploy reports a dirty tracked worktree on the VPS, do not reset automatically. Diagnose the dirty file first:

- temporary server edit: restore the repository version after human confirmation
- required runtime setting: migrate it to `.env` or an ignored runtime file
- uncertain change: stop and report the diff without printing secrets

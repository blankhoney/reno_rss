# CI/CD Specification

[English](SPEC-CICD.md) | [中文](SPEC-CICD.zh-CN.md)

## Background

Reno RSS / AI Reader has GitHub Actions checks, GHCR image publishing, a trusted VPS release transaction, and smoke tests. Pull requests run checks; a `push` to `refs/heads/main` runs checks and publishes digest-qualified images plus publication evidence. The `ci.yml` image job does not mutate a VPS. Manual request workflows create immutable request artifacts, and `trusted-deploy.yml` consumes a completed request only after validating its provenance and the canonical main CI publication for the requested SHA.

This specification records that current delivery contract and the evidence required to keep it working.

## Goals

- Deploy staging or production only through the verified trusted release workflow; pull request events and the canonical image build do not mutate a VPS.
- Keep the request inputs manual, then require `trusted-deploy.yml` to apply the `staging` or `production` GitHub Environment and perform secret-bearing execution. Production requires its environment approval.
- Build application images in GitHub Actions and pull them on the VPS from GHCR.
- Keep runtime secrets on the VPS or in GitHub Secrets; never print them in logs.
- Make failures easy to classify as checks, image build, SSH/secret, VPS dirty worktree, deploy, or smoke-test failures.

## Non-Goals

- No Kubernetes, self-hosted runner, or new deployment platform.
- No automatic production deploy from `main`.
- No Git history rewrite or server secret migration in the CI workflow.
- No MiniMax cost-incurring E2E checks in automated smoke tests.

## User Stories

- As the maintainer, when I submit a valid staging request for a successfully published SHA, the trusted workflow should execute after provenance and environment gates pass.
- As the maintainer, I should not perform a direct SSH deployment; the trusted workflow owns the single locked SSH transaction.
- As a visitor, the staging app should continue to provide the shared-user functional demo while keeping admin operations role-protected.
- As the maintainer, production should only change after a manual GitHub deployment approval.

## Functional Requirements

- `ci.yml` must run Python tests/lint, reader-web tests/build, Compose validation, and explicit Trivy high/critical vulnerability plus secret scanning.
- `ci.yml` must build and push `ai-reader-web`, `ai-reader-api`, and `ai-reader-worker` images to GHCR with canonical `sha-<full 40-character SHA>` tags (the short tag is a compatibility alias only).
- Pull request events run checks only. A `push` to `refs/heads/main` publishes images and immutable publication evidence; it does not deploy staging. A manual staging request is executed only when `trusted-deploy.yml` verifies the request and matching canonical publication.
- Fork PRs must not deploy and must not read deployment secrets.
- `deploy-staging.yml`, `deploy-prod.yml`, and `rollback.yml` remain manual request entries by explicit immutable `sha-<full SHA>` image tag and full deploy SHA. They only write fixed request artifacts.
- A production request additionally supplies three distinct trusted run IDs (staging deploy, rollback drill, and forward deploy), the different rollback-target SHA, the pinned current-main control-plane SHA, and the exact release-record ref plus SHA-256 digest. Its separate `trusted-production-promotion-proof` artifact is data only; the verifier must dereference the real successful receipt artifacts and release record, verify their provenance/content/digest, and bind them to the candidate and control-plane SHAs.
- `trusted-deploy.yml` must verify the completed request run, workflow identity/path, repository/ref/SHA, exact artifact, successful canonical `ci.yml` image publication for the operation, and a unique successful canonical CI run for the current-main control-plane SHA before its `execute` job can run.
- The `execute` job uses the `staging` or `production` GitHub Environment. Production cannot execute without the `production` environment approval and its scoped secrets.
- The trusted remote transaction must stop if the VPS tracked worktree is dirty, the pre-provisioned helper checksums do not match, or the operation SHA is not an ancestor of the fetched trusted `main` control-plane SHA.
- Staging smoke tests must verify containers, health endpoints, the public AI Reader workbench, anonymous articles `200`, and anonymous Admin `403` with non-mutating checks. They must not invoke actions that mark articles read, fetch content, sync, score, ask an agent, or mutate business data.

## Non-Functional Requirements

- **Security**: secrets, cookies, SSH keys, API keys, and Basic Auth headers must not be printed.
- **Traceability**: request artifacts must include the full deploy SHA and immutable image tag; the trusted orchestrator records images, target URL, and smoke-test success after execution.
- **Idempotence**: rerunning a deploy for the same image tag should converge services without manual cleanup.
- **Environment isolation**: staging automation must not deploy production.
- **Cost control**: automated smoke tests must not trigger LLM scoring or Agent calls.

## Interfaces and Boundaries

- **GitHub Actions**: `ci.yml` is the checks and image-publication path. `deploy-staging.yml`, `deploy-prod.yml`, and `rollback.yml` are manual request paths; their artifacts are data, not executable commands, and these jobs do not read deployment secrets. `trusted-deploy.yml` is the trusted execution path: its `verify` job checks the completed request run, allowlisted workflow identity/path, repository/ref/SHA, exact artifact, successful canonical `ci.yml` publication for the operation, and successful canonical CI for the current-main control plane. Only a successful verification enters `execute`, which checks out that exact control-plane SHA, declares the `staging` or `production` Environment, reads the scoped SSH/GHCR secrets, validates the exact known-hosts entry for `VPS_PORT`, and performs the remote transaction. The provenance gate remains before all deployment secrets and mutation.
- **Request artifact**: each manual request uploads one fixed JSON artifact with exactly `schema_version`, `request_type`, `environment`, `image_tag`, and `deploy_sha`. `schema_version` is `trusted-deploy-request/v1`; `image_tag` must be `sha-<40 lowercase hex>` and equal the full lowercase 40-character `deploy_sha`. Fixed artifact names are `trusted-staging-deploy-request`, `trusted-production-deploy-request`, and `trusted-rollback-request`.
- **Production promotion proof**: `deploy-prod.yml` also uploads `trusted-production-promotion-proof` (`trusted-production-promotion/v1`). It binds the candidate to three distinct staging runs: deploy candidate, rollback from candidate to a different target, and forward from that target to candidate. Receipt artifact names include environment, request type, run, and operation SHA. The release record must be exactly `<control-plane SHA>:docs/releases/<candidate SHA>.json`; its strict `rss-production-release/v1` content binds the candidate CI run/attempt, publication artifact ID and GitHub digest, three image digests, three run IDs, rollback target, and the backup/migration/rollback plan. `trusted-deploy.yml` validates the referenced runs, strict receipt archives, state transitions, release-record bytes, and digest; input fields or a manually asserted success status are not evidence by themselves.
- **Deployment inputs and secrets**: `execute` requires the configured `VPS_SSH_KEY` or `VPS_SSH_KEY_B64`, `VPS_HOST`, `VPS_PORT`, `VPS_USER`, `VPS_APP_DIR`, `VPS_KNOWN_HOSTS`, `GHCR_USERNAME`, and `GHCR_TOKEN`, plus repository variables containing the SHA-256 values for the pre-provisioned shared-lock wrapper, core, and transaction. Values are never printed. `VPS_KNOWN_HOSTS` is checked for the exact host and port; `ssh-keyscan` is not used.
- **Canonical shared lock**: before any remote filesystem mutation, the SSH command preflights the root-owned helper installation and invokes the public wrapper exactly once. The wrapper owns `/var/lib/reno-shared-vps/release-lock-v1/release.lock` for the complete transaction, including bundle intake, backup, Caddy/edge recovery, migrations, activation, probes, and compensation. Metadata is at `/var/lib/reno-shared-vps/release-lock-v1/metadata.json` and audit/quarantine is under `/var/lib/reno-shared-vps/release-lock-v1/audit/`. Workflow concurrency is only same-repository scheduling; it is not the VPS lock.
- **Bootstrap prerequisite**: a separately authorized, root-operated `infra/deploy/bootstrap-shared-release-v1.sh` must pre-provision the canonical lock tree and install the checksum-pinned root-owned helpers under `/usr/local/lib/reno-shared-vps/release-lock-v1/`. Unsafe ownership, permissions, symlinks, missing group, or checksum mismatch fail closed. Production, staging, rollback, and compensation do not invoke bootstrap.
- **Trusted remote deploy**: `.github/scripts/remote-deploy.sh` validates the locked manifest and the candidate bundle's embedded probe/edge/rollback contracts, logs in to GHCR, fetches `refs/heads/main`, requires the control-plane SHA to be that fetched main tip, and requires the operation SHA to be its ancestor. It verifies digest-qualified images and OCI revision before running the deploy, migration, backup, smoke, edge recovery, and runtime checks.
- **Production backup gate**: `infra/scripts/deploy.sh` verifies a fresh production database backup before its Compose pull/up, migration, or edge activation; backup or checksum failure stops the transaction with the current runtime intact.
- **Receipts and probes**: every transaction records verified cross-site receipts for `pre-mutation`, `pre-activation`, and either `post-activation`, `post-rollback`, or `post-compensation`. Each receipt binds contract version, `owner`, operation SHA, workflow run, phase, actual runtime SHA, UTC timestamp, fixed RSS/Blog URL results, and Caddy/edge state. The probe uses bounded HTTPS GETs with an allowlist: RSS must satisfy auth redirect then final HTTPS reachability, Blog must return public `200` over TLS, and Docker JSON inspection must prove Caddy's `myrss-app` and `brianstorm-edge` memberships, bridge drivers, loaded config, reachable RSS/Blog upstreams, production Blog membership, and no staging web on production edge. Unknown phases, unknown keys, invalid URLs, or any failed site/edge check produce no success receipt and block promotion.
- **Rollback provenance boundary**: the rollback request's operation SHA is the requested target runtime and must have canonical main publication evidence. The transaction records the actual pre-activation runtime as `rollbackFrom`; `post-rollback` binds runtime to the target, while `post-compensation` binds runtime to `rollbackFrom`. Compensation reads actual current runtime: it probes directly when already at `rollbackFrom`, activates `rollbackFrom` only when current equals the failed target, and refuses unknown state.
- **VPS runtime state**: `.env`, Authelia users, and other runtime secrets stay outside Git.

## Acceptance Criteria

- A `main` push produces a successful canonical `ci` image publication with three digest-qualified images and evidence bound to the full SHA.
- A valid staging request causes `trusted-deploy.yml` to pass provenance, declare the `staging` Environment, acquire the canonical VPS lock before mutation, and complete the remote deploy and cross-site receipts.
- A valid production request causes the same transaction under the approved `production` Environment; production is not changed by a `main` push alone.
- The staging public endpoint and its configured reader route render the functional demo; the trusted receipt also proves the RSS auth redirect/final reachability and Blog public route.
- An anonymous `GET /api/articles` returns `200`, while an anonymous Admin request returns `403`.
- Production remains unchanged unless the trusted workflow consumes a manually created `deploy-prod.yml` request, validates the current-SHA publication and all gates, and receives the `production` Environment approval.

## Operational Blocker Handling

If remote deploy reports a dirty tracked worktree on the VPS, do not reset automatically. Diagnose the dirty file first:

- temporary server edit: restore the repository version after human confirmation
- required runtime setting: migrate it to `.env` or an ignored runtime file
- uncertain change: stop and report the diff without printing secrets

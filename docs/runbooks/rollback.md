# Runbook: Rollback

> **Current boundary:** `rollback.yml` is request-only. It validates an immutable image tag and full deploy SHA, then uploads a JSON request artifact. It does not checkout code, read deployment secrets, request an environment approval, SSH to a VPS, or run `rollback.sh`.
>
> `trusted-deploy.yml` currently performs a verify-only provenance check for the completed rollback request. It does not declare an environment, read deployment secrets, SSH, or run `rollback.sh`; the secret-bearing rollback phase is **not enabled**. Running the request workflow does not roll back staging or production automatically.

## When to request a rollback

Create a rollback request when a confirmed deployment has one or more of these symptoms:

- Health checks fail after deployment.
- Authelia repeatedly restarts or rejects valid logins.
- Miniflux returns persistent 5xx errors.
- Critical scoring or worker errors make the application unusable.

A request is not evidence that a rollback happened. Wait for an enabled trusted orchestrator to report execution before treating the environment as changed.

## Identify the last known-good image

Use deployment evidence from the trusted deployment path, CI image publication, or an incident record. Record both values:

- `image_tag`: `sha-<7 lowercase hexadecimal characters>`.
- `deploy_sha`: the matching full 40-character lowercase commit SHA.

The tag must equal `sha-` plus the first seven characters of `deploy_sha`. Do not use a branch name, release ref, arbitrary tag, or an unverified short SHA. If the matching full SHA or image provenance is unknown, stop and escalate instead of creating a rollback request.

## Create the rollback request

1. Open **Actions → rollback → Run workflow**.
2. Set `env` to `staging` or `prod`.
3. Set `image_tag` to the immutable last-known-good tag.
4. Set `deploy_sha` to its matching full commit SHA.
5. Run the workflow and confirm that the fixed request artifact was uploaded.
6. Stop. Until the trusted orchestrator is enabled, no rollback follows this request.

The workflow rejects `git_ref`. Do not paste shell commands, SSH credentials, or secrets into inputs.

## Request artifact schema

The artifact is data, not an executable script. It uses the fixed `trusted-deploy-request/v1` schema and contains exactly:

```json
{
  "schema_version": "trusted-deploy-request/v1",
  "request_type": "rollback",
  "environment": "prod",
  "image_tag": "sha-abc1234",
  "deploy_sha": "0123456789abcdef0123456789abcdef01234567"
}
```

The fixed artifact name is `trusted-rollback-request`. A future trusted orchestrator must validate these fields as data and must not execute artifact contents.

## Residual provenance blocker

The verify-only `trusted-deploy.yml` path now validates request-run/artifact provenance and requires the rollback target to have successful canonical `ci.yml` main publication evidence. Secret-bearing rollback remains disabled until maintainer evidence confirms the workflow-ID allowlist, default-main protection, fixed production/staging Environment policies, and environment-scoped secrets. The remote contract uses fixed `refs/heads/main` ancestry (`.github/scripts/remote-deploy.sh:39-42,108-138`); do not restore arbitrary `git_ref` input or the retired `FETCH_HEAD^{commit} == DEPLOY_SHA` equality as a bypass.

## Stop conditions

Stop and report without retrying when:

- `env` is not exactly `staging` or `prod`.
- `deploy_sha` is not a full lowercase 40-character SHA.
- `image_tag` is not `sha-<7 lowercase hexadecimal characters>` or does not match the SHA prefix.
- The last-known-good image cannot be tied to a full SHA and trusted publication evidence.
- The request artifact is missing, has extra fields, or does not match `trusted-deploy-request/v1`.
- The secret-bearing trusted execution phase is not enabled. Verify-only provenance success is not a rollback result; do not claim a rollback or issue repeated requests to compensate.
- A later trusted execution reports a dirty tracked VPS worktree, a fetched-SHA mismatch, an image pull failure, or a migration/health-check failure. Do not reset the VPS or downgrade the database automatically.

## Post-rollback verification

Run these read-only checks only after an enabled trusted deployment path reports that the rollback actually executed:

```bash
# Internal health check
docker compose -p myrss-prod \
  -f infra/compose/docker-compose.base.yml \
  exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz

# Container status
docker ps --format "table {{.Names}}\t{{.Status}}" | grep myrss-prod
```

Expected: `OK` and all target containers are `Up` or healthy. If verification fails, preserve logs without exposing secrets and escalate to the incident procedure.

## Data safety

A container-image rollback must not alter the `postgres_data` volume. Database state is preserved across application image changes. If the failed deployment applied schema migrations, do not run an automatic downgrade; follow the migration-specific backup and restore procedure after human review.

## Authorized break-glass history

The former direct SSH and `infra/scripts/rollback.sh` path is archived operational knowledge only. It may be used solely under an explicitly authorized incident procedure with separate human verification of the image, full SHA, database state, and secret handling. It is prohibited for routine rollback, and this runbook does not provide a copy-paste direct-VPS command.

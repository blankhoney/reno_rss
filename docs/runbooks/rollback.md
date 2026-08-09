# Runbook: Rollback

> **Current boundary:** `rollback.yml` is request-only. It validates an immutable image tag and full deploy SHA, then uploads a JSON request artifact. It does not checkout code, read deployment secrets, request an environment approval, SSH to a VPS, or run `rollback.sh`.
>
> The trusted orchestrator that would consume the request and perform a secret-bearing rollback is **not enabled**. Running the workflow does not roll back staging or production automatically.

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

The current artifact carries `deploy_sha` but no trusted `DEPLOY_REF` or workflow-run/ref provenance claim. Once `main` advances, an old rollback SHA cannot satisfy the existing remote contract that requires a trusted `DEPLOY_REF` plus `FETCH_HEAD^{commit}` to equal `DEPLOY_SHA`. Rollback cannot be enabled or called usable until the trusted orchestrator defines either a trusted ref/provenance resolution flow or a safe SHA-based fetch contract. Do not restore arbitrary `git_ref` input as a bypass.

## Stop conditions

Stop and report without retrying when:

- `env` is not exactly `staging` or `prod`.
- `deploy_sha` is not a full lowercase 40-character SHA.
- `image_tag` is not `sha-<7 lowercase hexadecimal characters>` or does not match the SHA prefix.
- The last-known-good image cannot be tied to a full SHA and trusted publication evidence.
- The request artifact is missing, has extra fields, or does not match `trusted-deploy-request/v1`.
- The trusted orchestrator is not enabled. Do not claim a rollback or issue repeated requests to compensate.
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

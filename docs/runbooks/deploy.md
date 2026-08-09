# Runbook: Deploy

> **Current boundary:** the three manual deploy workflows are request-only. They validate input and upload a JSON request artifact; they do not checkout repository code, read deployment secrets, SSH to a VPS, or deploy containers.
>
> The trusted orchestrator that would consume these artifacts and perform secret-bearing deployment is **not enabled**. Creating a request does not deploy staging or production automatically.

## Current deployment paths

- **Staging normal path:** a successful `main` push runs `ci.yml`, which builds and publishes the images and performs the existing staging deployment path.
- **Manual staging path:** `deploy-staging.yml` creates a request artifact only. It is not a deployment fallback until a trusted orchestrator is enabled.
- **Manual production path:** `deploy-prod.yml` creates a request artifact only. Production remains unchanged; no `production` environment approval or secret-bearing deployment is performed by this workflow.
- **Rollback path:** `rollback.yml` creates a rollback request artifact only. See [rollback.md](./rollback.md).

Do not use SSH, `git pull`, `infra/scripts/deploy.sh`, or another direct VPS command as a routine substitute for the request workflow. The old direct path is retained only as an authorized incident break-glass procedure below.

## Request inputs

`deploy-staging.yml` and `deploy-prod.yml` require exactly:

- `image_tag`: an immutable tag in the form `sha-<7 lowercase hexadecimal characters>`.
- `deploy_sha`: the full 40-character lowercase commit SHA. Its first seven characters must match the suffix of `image_tag`.

`rollback.yml` has the same image fields and additionally requires `env`, which must be `staging` or `prod`.

The workflows reject malformed values before writing the artifact. They do not accept `git_ref`.

## Request artifact schema

Each request uploads one fixed JSON artifact. The artifact is data, not an executable script. The schema is `trusted-deploy-request/v1` and contains exactly these fields:

```json
{
  "schema_version": "trusted-deploy-request/v1",
  "request_type": "deploy",
  "environment": "staging",
  "image_tag": "sha-abc1234",
  "deploy_sha": "0123456789abcdef0123456789abcdef01234567"
}
```

`request_type` is `deploy` for the staging and production workflows. For `rollback.yml`, it is `rollback`; `environment` is the selected `staging` or `prod` value. Artifact names are fixed and are not derived from input values:

- `trusted-staging-deploy-request`
- `trusted-production-deploy-request`
- `trusted-rollback-request`

A future trusted orchestrator must validate this schema as data. It must not execute artifact contents.

## Creating a manual request

1. Open **Actions** and select `deploy-staging` or `deploy-prod`.
2. Select the intended workflow ref in GitHub. GitHub loads the workflow YAML from that dispatch ref; the request job does not checkout or execute target repository code and does not read deployment secrets.
3. Enter the immutable `image_tag` and its matching full `deploy_sha`.
4. Run the workflow and confirm that the request artifact was uploaded.
5. Stop. Until a trusted orchestrator is enabled, no deployment follows this workflow.

Before any trusted orchestrator is enabled, it must verify workflow-run/ref/artifact provenance: the artifact must come from the expected workflow run and dispatch ref, and its request data must remain bound to the validated immutable SHA. The current artifact schema does not itself carry a trusted ref or provenance claim.

For production, do not describe a successful request artifact as a production deployment or approval. There is currently no enabled path from this artifact to the production VPS.

## Stop conditions

Stop and report the request without retrying when:

- `deploy_sha` is not a full lowercase 40-character SHA.
- `image_tag` is not `sha-<7 lowercase hexadecimal characters>` or does not match the SHA prefix.
- `git_ref` is requested or appears in a manual request.
- A request workflow asks for `secrets.*`, SSH credentials, GHCR credentials, an `environment` approval, or repository checkout.
- The expected artifact is missing, has extra fields, does not match `trusted-deploy-request/v1`, or cannot be tied to the expected workflow run and dispatch ref through trusted provenance.
- Someone claims the request deployed an environment while the trusted orchestrator is not enabled.
- A later trusted deployment reports a dirty tracked VPS worktree. Do not reset it automatically; diagnose the changed file first.

## Post-deploy health checks

Run these checks only after an independent trusted deployment path reports that the target environment actually changed. They do not deploy or repair anything:

```bash
docker compose -p myrss-prod \
  -f infra/compose/docker-compose.base.yml \
  exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz
```

Expected: `OK`.

For production, inspect container state without printing environment values:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep myrss-prod
```

Expected: all target containers show `Up ... (healthy)` or `Up ...`. If health checks fail after a confirmed deployment, stop traffic changes and use [rollback.md](./rollback.md); do not run an unreviewed direct script.

## Authorized break-glass history

The former direct SSH path and direct `infra/scripts/deploy.sh`/`rollback.sh` invocation are archived operational knowledge, not the current workflow contract. They may be used only under an explicitly authorized incident procedure by an operator who has separately verified the repository revision, image availability, database migration impact, and secret handling. They must not be used for routine staging or production changes, and this runbook does not provide a copy-paste direct-deploy command.

## Other runtime administration

Creating the initial AI Reader admin and rotating a Miniflux API key are separate privileged runtime operations. Perform them only through their approved operational procedure after a real deployment is independently confirmed; never place recovery codes or API keys in chat, tickets, or logs.

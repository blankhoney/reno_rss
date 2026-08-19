# Runbook: Deploy

`deploy-staging.yml` and `deploy-prod.yml` are request entry points. They
validate inputs and upload a fixed JSON artifact; they do not read deployment
secrets or mutate a VPS. The subsequent `trusted-deploy.yml` workflow is the
actual release path: its `verify` job validates provenance, and its `execute`
job performs the secret-bearing, locked remote transaction. A successful
request artifact alone is not evidence that an environment changed.

## Preconditions

Before any staging or production release, the VPS must have the separately
authorized shared-lock bootstrap installed. The root-operated
`infra/deploy/bootstrap-shared-release-v1.sh` must have created and verified:

- `/var/lib/reno-shared-vps/release-lock-v1/`
- `/var/lib/reno-shared-vps/release-lock-v1/release.lock`
- `/var/lib/reno-shared-vps/release-lock-v1/audit/`
- `/usr/local/lib/reno-shared-vps/release-lock-v1/with-shared-release-lock.sh`
- `/usr/local/lib/reno-shared-vps/release-lock-v1/internal/shared-release-lock-core.sh`
- `/usr/local/lib/reno-shared-vps/release-lock-v1/trusted-remote-deploy.sh`

The lock root/audit and lock inode must have the contract ownership and modes;
helpers must be root-owned and checksum-pinned through repository variables.
Missing paths, symlinks, unsafe permissions, an unavailable `reno-deploy` group,
or a checksum mismatch stop the release. Staging, production, rollback, and
compensation workflows never bootstrap or repair this installation.
`metadata.json` is live ownership metadata created only while a transaction
holds the kernel lock; it is not a persistent bootstrap artifact.

## Request inputs

`deploy-staging.yml` and `deploy-prod.yml` require exactly:

- `image_tag`: an immutable tag in the form `sha-<40 lowercase hexadecimal characters>`.
- `deploy_sha`: the matching full 40-character lowercase commit SHA. It must be
  exactly the suffix of `image_tag`.

The request workflows reject malformed values and do not accept `git_ref`.
`rollback.yml` has the same image fields and additionally requires `env`, which
must be `staging` or `prod`.

`deploy-prod.yml` also requires:

- `staging_receipt_run`: staging deploy of the candidate;
- `rollback_receipt_run`: staging rollback from candidate to a different target;
- `forward_receipt_run`: staging forward deploy from that target to candidate;
- `rollback_target_sha`: that different full target SHA;
- `control_plane_sha`: the current-main full SHA containing the release record;
- `release_record_ref`: exactly
  `<control_plane_sha>:docs/releases/<deploy_sha>.json`;
- `release_record_digest`: the record's `sha256:<64 lowercase hex>` digest.

The three run IDs must be different. These inputs are references to evidence,
not claims that the evidence exists.

## Request artifact schema

Each request uploads one fixed JSON artifact. The artifact is data, not an
executable script. The schema is `trusted-deploy-request/v1` and contains
exactly these fields:

```json
{
  "schema_version": "trusted-deploy-request/v1",
  "request_type": "deploy",
  "environment": "staging",
  "image_tag": "sha-0123456789abcdef0123456789abcdef01234567",
  "deploy_sha": "0123456789abcdef0123456789abcdef01234567"
}
```

`request_type` is `deploy` for staging and production, and `rollback` for
`rollback.yml`. Artifact names are fixed and are not derived from input:

- `trusted-staging-deploy-request`
- `trusted-production-deploy-request`
- `trusted-rollback-request`

The canonical `ci.yml` publication must exist for the requested full SHA. Its
three GHCR images are consumed by digest, and OCI revision labels must match
that SHA. A short image tag is only a compatibility alias and is not a trusted
release reference.

For production, `deploy-prod.yml` also uploads the separate
`trusted-production-promotion-proof` artifact (`trusted-production-promotion/v1`).
The trusted verifier fetches the referenced trusted-deploy receipt archives and
release-record bytes, validates their status, provenance, SHA binding, and
digest, and rejects a proof whose inputs only assert success without matching
current GitHub evidence.

The release record uses strict schema `rss-production-release/v1`. It records
the repository, candidate and control-plane full SHAs; canonical candidate CI
workflow/run/attempt; publication artifact ID and GitHub SHA-256 digest; the
full image tag and three image digests; the three staging run IDs and rollback
target; and this exact plan contract:

- verified production backup before Compose or activation, checked by SHA-256;
- forward-only migrations gated by that verified backup;
- runtime-state-guarded rollback with post-rollback or post-compensation probe.

Unknown or incomplete release-record fields fail closed.

## Creating a release request

1. Open **Actions** and select `deploy-staging` or `deploy-prod`.
2. Enter the canonical full-SHA `image_tag` and its matching `deploy_sha`.
3. For production, enter the three staging run IDs, rollback target, current
   control-plane SHA, exact release-record ref, and release-record digest.
4. Run the workflow and confirm that the fixed request artifact (and, for
   production, the promotion-proof artifact) was uploaded.
5. Wait for the `workflow_run`-triggered `trusted-deploy` workflow. Do not run a
   direct SSH or VPS deployment as a substitute.

The `verify` job checks the allowlisted request workflow ID/path/name, completed
run status, repository/ref/SHA, exact artifact, and successful canonical `ci`
image publication from `refs/heads/main`. It also identifies the current main
control-plane SHA. `execute` checks out that exact control-plane SHA and builds a
bounded bundle containing the manifest plus the reviewed cross-site probe,
shared-edge recovery, and rollback-state contracts. Failed or ambiguous
provenance prevents `execute` from starting. For production, the same verifier
also validates the promotion proof's actual staging, rollback, and forward
receipt archives, their runtime transitions, and the strict release-record
content/digest before `execute` can start.

The `execute` job declares the `staging` or `production` GitHub Environment.
Production requires the `production` Environment approval before any
secret-bearing step can run. It then validates the deployment environment and
reads only the configured secrets/variables:

- `VPS_SSH_KEY` or `VPS_SSH_KEY_B64`
- `VPS_HOST`, `VPS_PORT`, `VPS_USER`, `VPS_APP_DIR`
- `VPS_KNOWN_HOSTS`
- `GHCR_USERNAME`, `GHCR_TOKEN`
- `SHARED_RELEASE_LOCK_WRAPPER_SHA256`
- `SHARED_RELEASE_LOCK_CORE_SHA256`
- `SHARED_RELEASE_LOCK_TRANSACTION_SHA256`

Secret values are never printed. The known-hosts file must contain the exact
configured host token for the actual `VPS_PORT` (`host` for port 22,
`[host]:port` otherwise). Trust is not learned from the network and
`ssh-keyscan` is prohibited.

## Locked remote transaction

The execute job sends one credential frame and one bounded, secret-free bundle
to a single SSH command. Before any remote filesystem mutation, that command
read-only preflights the pre-provisioned helper paths and checksums, then calls
the public `with-shared-release-lock.sh` exactly once. The public wrapper opens
and holds the canonical kernel flock for the entire transaction; there is no
outer workflow flock and no per-step lock reacquisition.

The lock covers bundle intake and validation, GHCR login, backup, Caddy/shared
edge recovery, migration, activation, smoke checks, receipts, and rollback or
compensation. The remote transaction fails closed if the VPS worktree is dirty,
the fetched `refs/heads/main` tip is not the trusted control-plane SHA, the
operation SHA is not its ancestor, an image digest/OCI revision is wrong, or a
runtime check fails.

For production, `infra/scripts/deploy.sh` performs and verifies a fresh database
backup before its Compose pull/up, migration, or edge activation. A backup or
checksum failure stops the transaction while the currently running revision is
still intact.

The fixed lock contract is shared with Blog:

- root: `/var/lib/reno-shared-vps/release-lock-v1`
- kernel lock: `.../release.lock`
- live metadata: `.../metadata.json`
- audit/quarantine: `.../audit/`

The live flock is authoritative. Metadata records contract version, owner/repo,
operation SHA, workflow run, token, timestamps, process IDs, lock path, and
audit state. TTL is diagnostic only; a live flock cannot be stolen. Release is
allowed only for an exact owner/token match, and missing or mismatched metadata
is audited rather than removed blindly.

## Post-deploy evidence

After the bundle is received under the lock, the transaction invokes the
embedded fixed cross-site probe as `pre-mutation`, before edge recovery, GHCR
login, control-plane checkout, or activation. It invokes the same probe again
after edge recovery but before activation, and after activation. It writes
verified receipts for these phases:

- `pre-mutation`: the candidate-bundle probe, fixed public routes, edge state,
  and actual current runtime SHA before the release transaction proceeds.
- `pre-activation`: shared-edge recovery and public verification are complete;
  runtime is still the current SHA.
- `post-activation`: runtime equals the operation/candidate SHA.

Every receipt has `contractVersion: 1`, `owner.project`, `owner.repo`, the full
operation SHA, positive `workflowRun`, phase, actual runtime full SHA, UTC
timestamp, and the fixed RSS/Blog URL and edge results. The URL probe performs
bounded HTTPS GETs with a pre-request allowlist: RSS must satisfy the auth
redirect and final HTTPS reachability contract; Blog must return public `200`
over TLS. Docker JSON inspection must prove Caddy `myrss-edge-caddy-1` is on
both `myrss-app` and `brianstorm-edge`, both networks use the bridge driver,
config and both upstreams are reachable, production Blog is on the production
edge, and `brianstorm-staging-web` is not on it. Any failure produces no success
receipt and blocks promotion. The workflow persists only validated receipt
JSON as its evidence artifact.

After a successful staging transaction, run the non-mutating runtime proof when
it is enabled for the release and confirm the public staging reader route. For
production, confirm the public RSS and Blog routes from the trusted receipt and
inspect container health through the approved operational access path without
printing environment values.

## Stop conditions

Stop and report without retrying when:

- the request SHA/tag is malformed, short, or not tied to canonical CI
  publication evidence;
- a production promotion proof is missing, expired, not bound to the candidate
  and control-plane SHAs, or does not validate the actual staging/rollback/
  forward receipts and strict release-record content/digest;
- request workflow identity, artifact, repository/ref/SHA, or run status does
  not match the allowlist;
- required environment approval, secret, known-host entry, helper checksum, or
  canonical lock path is missing;
- a VPS tracked worktree is dirty or the remote control-plane/operation ancestry
  check fails;
- either public site, Caddy network/config/upstream check, staging-contamination
  check, migration, smoke check, or receipt validation fails.

Do not reset a dirty VPS automatically and do not use direct `git pull`,
`infra/scripts/deploy.sh`, or a bare SSH command as a routine bypass. Preserve
non-sensitive diagnostics and use the rollback request path after the current
runtime is independently confirmed.

## Authorized break-glass history

The former direct SSH and direct `infra/scripts/deploy.sh` paths are archived
incident knowledge only. They require explicit incident authorization and
separate verification of repository revision, image provenance, database impact,
and secret handling. They are not a routine staging or production path and are
not a substitute for the shared-lock transaction.

Creating the initial AI Reader admin and rotating a Miniflux API key are
separate privileged runtime operations. Perform them only through their approved
procedure after a real deployment is independently confirmed; never put recovery
codes or API keys in chat, tickets, or logs.

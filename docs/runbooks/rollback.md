# Runbook: Rollback

`rollback.yml` is the manual rollback request entry point. It validates an
immutable target image tag and full SHA, then uploads a fixed JSON artifact. The
request workflow itself does not read deployment secrets or mutate a VPS. Its
completed run triggers `trusted-deploy.yml`; after provenance and environment
gates, the trusted `execute` job performs the actual rollback under the shared
VPS lock.

## Preconditions and evidence

Rollback is permitted only after the target image and full SHA are tied to a
successful canonical `ci.yml` publication on `refs/heads/main`. The VPS must
already have the canonical shared-lock tree and checksum-pinned helpers
installed by the separately authorized root bootstrap. Rollback and
compensation never bootstrap, repair, or bypass that installation.

Do not treat a request artifact, a successful `verify` job, an old image tag, or
a stale receipt as proof that rollback occurred. The trusted execution must
produce current-run receipts and a runtime proof bound to the operation SHA.

## When to request a rollback

Create a rollback request when a confirmed deployment has one or more of these
symptoms:

- health or public cross-site probes fail after activation;
- Authelia repeatedly restarts or rejects valid logins;
- Miniflux returns persistent 5xx errors;
- critical scoring or worker errors make the application unusable;
- the Caddy shared-edge contract, Blog route, or staging/production network
  separation is no longer valid.

Before requesting, preserve the current deployment evidence without printing
secrets and identify the last known-good full SHA and digest-qualified images.

## Identify the rollback target

Record the requested target as:

- `image_tag`: `sha-<40 lowercase hexadecimal characters>`;
- `deploy_sha`: the matching full 40-character lowercase commit SHA.

The tag must equal `sha-` plus the entire `deploy_sha`. Do not use a branch name,
release ref, arbitrary short SHA, or an image without canonical publication and
digest evidence. If the target SHA or its publication cannot be verified, stop
instead of creating a request.

## Create the rollback request

1. Open **Actions → rollback → Run workflow**.
2. Set `env` to `staging` or `prod`.
3. Set `image_tag` to the immutable last-known-good target tag.
4. Set `deploy_sha` to its matching full commit SHA.
5. Run the workflow and confirm that `trusted-rollback-request` was uploaded.
6. Wait for the completed request to trigger `trusted-deploy`; do not run a
   direct SSH command or a bare `infra/scripts/rollback.sh` invocation.

For a production rollback, the trusted execute job declares the `production`
GitHub Environment and cannot proceed without its approval. Staging declares
the `staging` Environment. The execute job validates exact `VPS_KNOWN_HOSTS`
for `VPS_PORT`, the checksum-pinned helpers, GHCR credentials, and the
canonical lock before any remote mutation. It does not use `ssh-keyscan`.

## Request artifact schema

The artifact is data, not an executable script. It uses the fixed
`trusted-deploy-request/v1` schema and contains exactly:

```json
{
  "schema_version": "trusted-deploy-request/v1",
  "request_type": "rollback",
  "environment": "prod",
  "image_tag": "sha-0123456789abcdef0123456789abcdef01234567",
  "deploy_sha": "0123456789abcdef0123456789abcdef01234567"
}
```

The fixed artifact name is `trusted-rollback-request`. The trusted verifier
binds the request workflow identity/path, completed run, repository/ref/SHA,
artifact, current-main control-plane SHA, and canonical publication evidence
before the execute job receives deployment secrets. The execute bundle embeds
the reviewed probe, edge-recovery, and rollback-state contracts from that
control-plane SHA.

## Locked rollback transaction

The trusted remote transaction receives the bounded candidate bundle under the
lock and invokes the public
`/usr/local/lib/reno-shared-vps/release-lock-v1/with-shared-release-lock.sh`
exactly once. It acquires and holds the canonical flock at
`/var/lib/reno-shared-vps/release-lock-v1/release.lock` across bundle intake,
backup, Caddy/edge recovery, GHCR login, image verification, migrations,
activation, probes, and compensation. The lock is shared with Blog; GitHub
workflow concurrency does not replace it.

Before activation it fetches trusted `refs/heads/main`, verifies the control
plane is the expected main SHA, and confirms the operation SHA is an ancestor.
It captures the actual current runtime and its digest-qualified images as the
rollback source before changing services. Image OCI revision and runtime SHA
must agree with the requested target after activation.

For a production rollback, `infra/scripts/deploy.sh` requires a fresh verified
database backup before its Compose pull/up, migration, or edge activation. A
backup or checksum failure stops the transaction before that deployment step.

## Runtime-bound rollback state machine

Use these terms in receipts and incident notes:

- `operation`: the workflow/request SHA and desired rollback target.
- `rollbackFrom`: the actual runtime SHA observed immediately before the
  rollback activation attempt.
- `target`: the operation SHA; it must equal the requested rollback target.

The transaction emits `pre-mutation` from the embedded candidate-bundle probe
before edge recovery, GHCR login, control-plane checkout, or activation, then
emits `pre-activation` after edge recovery. Both receipts contain the actual
current runtime. A successful rollback emits `post-rollback`
with runtime equal to `target`. Each rollback receipt includes
`rollbackFrom` and `target`; it is not valid to substitute a workflow SHA for
the actual runtime source.

If activation, edge recovery, or the final probe fails, compensation does not
assume that the target became active. It reads actual current runtime and:

1. if current equals `rollbackFrom`, it does not activate anything and emits a
   `post-compensation` probe for that runtime;
2. if current equals `target`, it activates `rollbackFrom` with `target` as the
   expected current value, verifies the restored runtime, and emits
   `post-compensation` for `rollbackFrom`;
3. if current is any other or unknown SHA, it fails closed without activation
   or a success receipt.

A post-compensation read closes the race guard. Any failure of the shared edge,
RSS auth redirect/final reachability, Blog public `200`/TLS route, Caddy
membership/driver/config/upstream, or staging contamination check blocks
promotion and keeps the incident in compensation handling.

## Receipt contract

The validated receipt contract is version 1. Every receipt binds owner/repo,
operation full SHA, positive workflow run, phase, actual runtime full SHA, UTC
timestamp, fixed RSS and Blog URL results, and edge state. Allowed phases are:

- `pre-mutation`
- `pre-activation`
- `post-rollback`
- `post-compensation`

The fixed probe uses bounded HTTPS GETs and validates each redirect target before
requesting it. RSS must show the expected authentication redirect and final
allowlisted HTTPS reachability; Blog must be public `200` over TLS. Docker JSON
inspection must prove `myrss-edge-caddy-1` is attached to both `myrss-app` and
`brianstorm-edge`, both use the bridge driver, config is loaded, both upstreams
are reachable, production Blog is on the production edge, and staging web is
not attached to that production edge. Any failed check is non-zero and no
success receipt is accepted.

## Stop conditions

Stop and report without retrying when:

- `env` is not `staging` or `prod`;
- the target tag/SHA is not a full-SHA canonical pair;
- target publication, request-run provenance, artifact, environment approval,
  known-host entry, helper checksum, or canonical lock precondition is missing;
- the VPS worktree is dirty or control-plane/operation ancestry fails;
- the actual current runtime is unknown or neither `rollbackFrom` nor `target`;
- any migration, image, runtime, public route, edge, probe, or receipt check
  fails.

Do not reset the VPS, downgrade PostgreSQL, remove the lock metadata blindly, or
repeat requests as compensation. Preserve non-sensitive evidence and escalate
through the incident procedure.

## Data safety

A container-image rollback does not alter the `postgres_data` volume. If the
failed deployment applied schema migrations, do not run an automatic downgrade;
follow the migration-specific backup and restore procedure after human review.
The shared transaction retains its backup and audit evidence for the approved
recovery path.

## Authorized break-glass history

The former direct SSH and direct `infra/scripts/rollback.sh` path is archived
incident knowledge only. It may be used solely under explicit incident
authorization with separate verification of the image, full SHA, database
state, shared edge, lock state, and secret handling. It is prohibited for
routine rollback and is not a substitute for the trusted locked transaction.

# Learning notes

## 2026-08-20 — Final release candidate

- The original `my_rss` checkout remains an immutable evidence source. Release
  work is migrated into a clean branch rooted in the current remote `main`.
- Project skills are authoritative under `.agents/skills`. `.claude/skills`
  contains compatibility entrypoints only, and CI validates the authoritative
  packages directly.
- Release evidence is valid only when it binds the repository, workflow run,
  run attempt, full candidate SHA, artifact digest, and freshness boundary.
- Staging and production remain fail-closed until the shared-VPS lock and
  cross-site edge/probe contract are installed and tested.
- Shared-edge recovery only restores the fixed Caddy container on the existing
  RSS and Blog production bridge networks. It never mutates Blog containers,
  refuses a missing production Blog member, and rejects staging membership on
  the production Blog edge.
- Shared-edge receipts use contract v1, fixed HTTPS GET allowlists, full SHA
  identity, strict Docker inspect parsing, and active Caddy Admin configuration
  evidence. A missing RSS auth redirect, Blog 200, TLS verification, upstream,
  network membership, bridge driver, or production route fails the transaction.
- Redirect allowlisting happens before every HTTPS request and rejects userinfo,
  IP literals, non-443 ports, and unknown hosts; final URL validation is not a
  substitute for pre-request SSRF prevention.
- Cross-project mutations use one Linux `flock` wrapper around the complete
  remote transaction. The live file descriptor is authoritative over TTL;
  residual metadata is quarantined only after acquiring the lock, and release
  requires the exact owner, repository, SHA, run, and random token.
- CI runs the lock, recovery, and cross-site contract fixtures together on
  Ubuntu so macOS environments without `flock` cannot be mistaken for release
  evidence.
- Shared Caddy compose declares both production networks and no longer performs
  an unconditional force-recreate during an RSS business deploy. Any required
  compose activation is followed by the fixed recovery gate before reload.
- SSH trust is pre-provisioned rather than learned at deploy time. The exact
  OpenSSH host token must exist for the configured port (`host` for 22 or
  `[host]:port` otherwise); bare-host fallback on a non-default port is rejected.
- PostgreSQL snapshot-restore evidence retains `pg_restore` stderr and logs
  safe observed migration/fixture identifiers before exact fail-closed checks,
  so a failed restore artifact is diagnostic evidence rather than a success
  receipt. The disposable verification database is dropped before and after
  every attempt.
- Trusted deploy transport contains only a strict, secret-free manifest after
  a bounded credential frame. The VPS receives and validates it inside the
  canonical lock; no remote temporary file, checkout, backup, migration, edge
  change, activation, probe, compensation, or cleanup runs outside that lock.
- A release operation SHA names the immutable runtime images, while a separate
  control-plane SHA pins the current trusted `main` deployment scripts. This is
  especially important for rollback: old images never reintroduce old lock,
  edge, probe, or compensation behavior.
- The canonical shared-lock bootstrap is a separately approved production
  maintenance action. It streams a bounded three-file bundle directly into a
  root-only bootstrap, serializes first use, takes the canonical flock before
  unpacking, preserves the lock inode, and atomically installs checksum-bound
  helpers without a pre-lock remote landing directory.
- A selection-create retry compares the current color and ordered tags with its
  immutable journal snapshot. It issues a follow-up update only when metadata
  changed, avoiding a redundant request while preserving edits made before a
  retry.
- The trusted deploy bundle carries the exact provenance-bound edge verifier,
  edge recovery helper, and rollback state machine alongside its manifest.
  This permits a read-only `pre-mutation` receipt before edge repair, Git
  checkout, registry login, image pull, backup, migration, or activation; all
  later failures still use the same bundled compensation contract.
- Production backup and checksum verification complete before any new Caddy or
  application revision starts. A backup failure therefore leaves the running
  revision untouched instead of producing a snapshot after new code may have
  written to the old schema.
- Production promotion is a three-transition proof, not one claimed drill:
  staging activates the candidate from a different target, rollback restores
  that target from the candidate, and forward activates the candidate again.
  The release record lives at the later pinned control-plane SHA and binds the
  candidate CI run/attempt, GitHub artifact digest, image digests, run IDs, and
  backup/migration/rollback plan before production approval can execute. Its
  Git ref binds the containing control-plane commit externally; the JSON must
  not attempt an impossible self-reference to its own containing commit SHA.
- GNU `stat -fLc %T` may report the local ext filesystem magic literally as
  `ext2/ext3`. All three shared-lock entrypoints accept that exact local value
  while continuing to reject network, distributed, or unknown filesystems and
  preserving the same-device and canonical-FD gates.
- A production release transaction must have one backup authority. The locked
  remote transaction creates an exclusive backup before shared-state mutation,
  then passes operation-bound, mode-0600 evidence to `deploy.sh` for checksum
  revalidation. Creating a second timestamp-only backup can overwrite the first.
- Compensation before the `pre-activation` gate has a different truthful
  receipt shape from activation failure: it records only `pre-mutation` and
  `post-compensation`, preserving audit evidence without inventing a phase that
  never completed.
- Browser installation is a release gate and must be bounded like a test. CI
  installs the Chromium, Firefox, and WebKit dependencies separately, limits
  both steps, and retries bounded browser downloads so a stalled external CDN
  cannot occupy a runner indefinitely or hide which phase failed.
- Linux shared-lock tests pre-pull their fixed fixture image under a hard timeout
  and then run serially under a second timeout. This keeps signal/flock timing
  deterministic and prevents an implicit Docker Hub pull from looking like a
  hung lock implementation.

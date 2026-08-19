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

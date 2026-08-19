# PostgreSQL performance baseline freshness

## Responsibility and signal

The repository owner, or a maintainer explicitly designated by the repository owner, must inspect the latest `performance-baseline-freshness` workflow run every week.

The guaranteed signal is the workflow status and run summary in GitHub Actions. Email and web notifications are supplementary only when that responsible person's GitHub watch/notification settings are enabled. If no external notification channel is configured, the known limitation is that the weekly manual check can be missed; the workflow must not be described as an actively delivered alert.

## What the check proves

The workflow is read-only. It reads the canonical repository, the registered numeric `ci` workflow identity, canonical-main run/job metadata, and artifact metadata. It does not download, copy, re-upload, or create a baseline.

Canonical-main production is performed only by the independent CI job named `canonical PostgreSQL performance baseline producer`. It has its own PostgreSQL service, schema migration, fixture seed, measurement, and `db-postgres-performance-baseline-main` upload; it runs only for `blankhoney/reno_rss` pushes to `main` and has no dependency on the large `checks` job. Pull-request `checks` produces only the candidate and then resolves and compares the trusted canonical artifact, so it never uploads the canonical artifact or races to consume its own run.

Artifact and attempt-job enumeration must read every page and prove that every page reports the same non-negative `total_count`. The final number of unique records must equal that count. A missing `Link` with uncollected records, count drift, duplicate IDs, a page cap, or a partial request fails closed and cannot justify comparison or bootstrap.

Candidate fallback is deliberately narrow. The resolver may skip only a canonical producer that is explicitly not completed yet, an artifact confirmed expired or inside the expiry safety margin, or an exact artifact metadata/download 404 or 410 race. Repository, workflow, run, job, artifact, digest, ZIP, JSON, payload run/attempt/SHA, or other provenance mismatches fail immediately; the resolver must not fall back to an older baseline or bootstrap on `main`.

Trust is anchored to the successful independent producer job, not the final workflow conclusion: a later unrelated job failure or cancellation does not invalidate a completed successful producer. The repository, workflow, run, attempt, full SHA, producer-job identity, REST artifact metadata, computed SHA-256 digest, and freshness checks remain mandatory.

Freshness uses the artifact REST `expires_at` value. The check fails when no trusted baseline exists, the artifact is expired, or less than 14 days remain. It does not infer expiry from `retention-days: 90`.

## Response to a failed check

1. Confirm the failure is not a permission, pagination, trust-registration, or GitHub API error. Those conditions fail closed and do not prove that a baseline is absent.
2. Inspect the latest canonical `main` CI run and its summary. A successful comparison run is the normal refresh path.
3. If no baseline exists, use only a reviewed, real change on canonical `main` that is not excluded by the current CI path filters. Do not assume that a docs-only or empty commit triggers CI.
4. Confirm the independent producer job completed successfully and uploaded `db-postgres-performance-baseline-main` with an actual REST `expires_at` and digest. A later unrelated workflow failure or cancellation is not itself a reason to reject that artifact.
5. Confirm a later PR runs `mode=comparison`. Do not copy a PR candidate, a fork artifact, or a failed-run artifact into the baseline role.

⚠️ Do not disable digest, provenance, pagination, or comparison checks to refresh the signal. Do not use `continue-on-error`, manually upload an archive, modify branch protection, or rerun an old workflow as a substitute for a new trusted producer run.

# Shared release lock v1 bootstrap

Only a privileged, one-time VPS maintenance action may run
`infra/deploy/bootstrap-shared-release-v1.sh`. Production, staging, rollback,
and compensation workflows must never invoke it.

The fixed contract paths are:

- `/var/lib/reno-shared-vps/release-lock-v1/release.lock`
- `/var/lib/reno-shared-vps/release-lock-v1/metadata.json`
- `/var/lib/reno-shared-vps/release-lock-v1/audit/`
- `/usr/local/lib/reno-shared-vps/release-lock-v1/`

Create the `reno-deploy` group through the separately approved host bootstrap.
Then run the bootstrap as root with three checked-in, non-symlink sources:

```sh
sudo infra/deploy/bootstrap-shared-release-v1.sh \
  --public-source infra/deploy/with-shared-release-lock.sh \
  --public-sha256 EXPECTED_PUBLIC_SHA256 \
  --core-source infra/deploy/internal/shared-release-lock-core.sh \
  --core-sha256 EXPECTED_CORE_SHA256 \
  --transaction-source /approved/path/to/trusted-remote-deploy.sh \
  --transaction-sha256 EXPECTED_TRANSACTION_SHA256
```

It creates root and audit as `root:reno-deploy` mode `0770`, and the lock as
`root:reno-deploy` mode `0660`. Existing unsafe ownership, modes, or symlinks
are rejected rather than repaired. It holds the existing canonical flock while
atomically installing root-owned read-only helpers; it never replaces the lock
inode. The installed paths are exactly
`with-shared-release-lock.sh`, `internal/shared-release-lock-core.sh`, and
`trusted-remote-deploy.sh` under the helper root. Obtain each expected SHA-256
from the reviewed deployment bundle, not from the bootstrap host. The audit is
a unique `O_EXCL` JSON file in the verified audit directory and records only
event, timestamp, canonical lock path, and source checksums—never source
contents, users, or secrets.

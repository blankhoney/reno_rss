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
For remote installation, send a reviewed bounded tar bundle on stdin. It must
contain exactly `with-shared-release-lock.sh`,
`internal/shared-release-lock-core.sh`, and `trusted-remote-deploy.sh` as
regular files, plus the independently reviewed SHA-256 values:

```sh
tar -cf - with-shared-release-lock.sh internal/shared-release-lock-core.sh trusted-remote-deploy.sh |
sudo infra/deploy/bootstrap-shared-release-v1.sh --bundle-stdin \
  --public-sha256 EXPECTED_PUBLIC_SHA256 \
  --core-sha256 EXPECTED_CORE_SHA256 \
  --transaction-sha256 EXPECTED_TRANSACTION_SHA256
```

On an initial host, add `--create-group`; `--add-sudo-user` adds only the
strictly validated invoking `SUDO_USER` to `reno-deploy` and records only a
boolean in audit. Local maintenance may use the three `--*-source` arguments
instead of `--bundle-stdin`, with the same expected checksums.

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

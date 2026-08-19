import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const hasDocker = (() => { try { execFileSync('docker', ['version'], { stdio: 'ignore' }); return true; } catch { return false; } })();
const bootstrap = resolve('infra/deploy/bootstrap-shared-release-v1.sh');
function linux(name, body) {
  test(name, { skip: !hasDocker }, () => {
    const setup = "set -euo pipefail; groupadd reno-deploy; mkdir /sources; cp /work/infra/deploy/with-shared-release-lock.sh /sources/public.sh; cp /work/infra/deploy/internal/shared-release-lock-core.sh /sources/core.sh; printf '%s\\n' '#!/usr/bin/env bash' 'exit 0' >/sources/transaction.sh; chmod 0755 /sources/*; sum() { sha256sum \"$1\" | awk '{print $1}'; }; run() { /work/infra/deploy/bootstrap-shared-release-v1.sh --public-source /sources/public.sh --public-sha256 \"$(sum /sources/public.sh)\" --core-source /sources/core.sh --core-sha256 \"$(sum /sources/core.sh)\" --transaction-source /sources/transaction.sh --transaction-sha256 \"$(sum /sources/transaction.sh)\"; }; ";
    execFileSync('docker', ['run', '--rm', '-v', `${resolve('.') }:/work:ro`, 'node:22-bookworm', 'bash', '-lc', setup + body], { stdio: 'pipe' });
  });
}

linux('first install creates the three exact helper paths and canonical permissions', "run; test \"$(stat -Lc '%U:%G:%a' /var/lib/reno-shared-vps/release-lock-v1)\" = root:reno-deploy:770; test \"$(stat -Lc '%U:%G:%a' /var/lib/reno-shared-vps/release-lock-v1/release.lock)\" = root:reno-deploy:660; test -f /usr/local/lib/reno-shared-vps/release-lock-v1/with-shared-release-lock.sh; test -f /usr/local/lib/reno-shared-vps/release-lock-v1/internal/shared-release-lock-core.sh; test -f /usr/local/lib/reno-shared-vps/release-lock-v1/trusted-remote-deploy.sh; test ! -e /usr/local/lib/reno-shared-vps/release-lock-v1/shared-release-lock-core.sh; test ! -e /usr/local/lib/reno-shared-vps/release-lock-v1/transaction.sh; test -n \"$(find /var/lib/reno-shared-vps/release-lock-v1/audit -name '*-bootstrap.json' -print)\"");
linux('upgrade preserves the lock inode and safely completes a partial first creation', "mkdir -p /var/lib/reno-shared-vps/release-lock-v1; chown root:reno-deploy /var/lib/reno-shared-vps/release-lock-v1; chmod 0770 /var/lib/reno-shared-vps/release-lock-v1; run; inode=$(stat -Lc %i /var/lib/reno-shared-vps/release-lock-v1/release.lock); printf '%s\\n' '#!/usr/bin/env bash' '# replacement' >/sources/public.sh; chmod 0755 /sources/public.sh; run; test \"$inode\" = \"$(stat -Lc %i /var/lib/reno-shared-vps/release-lock-v1/release.lock)\"; grep -qx '# replacement' /usr/local/lib/reno-shared-vps/release-lock-v1/with-shared-release-lock.sh; test -z \"$(find /usr/local/lib/reno-shared-vps/release-lock-v1 -name '.*.tmp' -print)\"");
linux('concurrent flock and unsafe permissions are rejected without repair', "run; flock /var/lib/reno-shared-vps/release-lock-v1/release.lock -c 'sleep 1' & holder=$!; sleep .1; if run; then exit 1; fi; wait \"$holder\"; chmod 0666 /var/lib/reno-shared-vps/release-lock-v1/release.lock; if run; then exit 1; fi; test \"$(stat -Lc %a /var/lib/reno-shared-vps/release-lock-v1/release.lock)\" = 666");
linux('checksum mismatch and symlinked audit cannot alter helpers or write outside audit', "run; before=$(sum /usr/local/lib/reno-shared-vps/release-lock-v1/with-shared-release-lock.sh); if /work/infra/deploy/bootstrap-shared-release-v1.sh --public-source /sources/public.sh --public-sha256 $(printf '0%.0s' {1..64}) --core-source /sources/core.sh --core-sha256 \"$(sum /sources/core.sh)\" --transaction-source /sources/transaction.sh --transaction-sha256 \"$(sum /sources/transaction.sh)\"; then exit 1; fi; test \"$before\" = \"$(sum /usr/local/lib/reno-shared-vps/release-lock-v1/with-shared-release-lock.sh)\"; ln -s /tmp/audit-outside /var/lib/reno-shared-vps/release-lock-v1/audit/bootstrap-audit.jsonl; run; test ! -e /tmp/audit-outside; test -n \"$(find /var/lib/reno-shared-vps/release-lock-v1/audit -name '*-bootstrap.json' -print)\"");
test('production workflows never call bootstrap', () => {
  const output = execFileSync('bash', ['-lc', "rg -n 'bootstrap-shared-release-v1' .github/workflows || true"], { encoding: 'utf8' });
  assert.equal(output, '');
  assert.match(bootstrap, /infra\/deploy\/bootstrap-shared-release-v1\.sh$/);
});
test('bootstrap preflights the same local filesystem and symlink gates before flock', () => {
  const source = readFileSync(bootstrap, 'utf8');
  assert.match(source, /\[\[ "\$\(uname -s\)" == Linux \]\]/);
  assert.match(source, /ext2\|ext3\|ext4\|xfs\|btrfs\|tmpfs\|overlayfs/);
  assert.match(source, /root_device=.*LOCK_ROOT/);
  assert.match(source, /root, lock, and audit must share one local filesystem/);
  assert.match(source, /helper directory must not be symbolic-linked/);
  assert.match(source, /helper subdirectory must not be symbolic-linked/);
});

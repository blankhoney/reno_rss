"""Multi-account daily LLM cost ledger (score / ask / agent) — GOAL §4.D."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime


ACCOUNTS = ("score", "ask", "agent")


@dataclass
class CostLedger:
    """Process-local durable-enough day buckets; API can mirror into app_settings later."""

    limits: dict[str, int] = field(
        default_factory=lambda: {"score": 200, "ask": 80, "agent": 20}
    )
    _usage: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(dict))

    def _day_key(self, day: date | None = None) -> str:
        return (day or datetime.now(UTC).date()).isoformat()

    def used(self, account: str, *, day: date | None = None) -> int:
        return int(self._usage.get(self._day_key(day), {}).get(account, 0))

    def remaining(self, account: str, *, day: date | None = None) -> int:
        limit = int(self.limits.get(account, 0))
        if limit <= 0:
            return 10**9
        return max(0, limit - self.used(account, day=day))

    def can_charge(self, account: str, units: int = 1, *, day: date | None = None) -> bool:
        if account not in ACCOUNTS:
            raise ValueError(f"unknown account: {account}")
        limit = int(self.limits.get(account, 0))
        if limit <= 0:
            return True
        return self.used(account, day=day) + max(0, units) <= limit

    def charge(self, account: str, units: int = 1, *, day: date | None = None) -> int:
        if account not in ACCOUNTS:
            raise ValueError(f"unknown account: {account}")
        if units < 0:
            raise ValueError("units must be non-negative")
        if not self.can_charge(account, units, day=day):
            raise RuntimeError(f"daily budget exceeded for {account}")
        key = self._day_key(day)
        bucket = self._usage.setdefault(key, {})
        bucket[account] = int(bucket.get(account, 0)) + units
        return bucket[account]

    def snapshot(self, *, day: date | None = None) -> dict[str, object]:
        day_key = self._day_key(day)
        accounts: dict[str, object] = {}
        for account in ACCOUNTS:
            limit = int(self.limits.get(account, 0))
            used = self.used(account, day=day)
            accounts[account] = {
                "used": used,
                "limit": limit,
                "remaining": self.remaining(account, day=day),
            }
        return {
            "day": day_key,
            "accounts": accounts,
            "accounting": "process_memory",
        }

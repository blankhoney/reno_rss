from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from threading import Lock


class DailyCallBudget:
    def __init__(
        self,
        limit: int,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.limit = max(0, int(limit))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = Lock()
        self._day = self._today()
        self._used = 0

    def try_consume(self, amount: int = 1) -> bool:
        if amount <= 0:
            return True
        with self._lock:
            self._reset_if_needed()
            if self.limit == 0:
                return True
            if self._used + amount > self.limit:
                return False
            self._used += amount
            return True

    def remaining(self) -> int | None:
        with self._lock:
            self._reset_if_needed()
            if self.limit == 0:
                return None
            return max(self.limit - self._used, 0)

    @property
    def used(self) -> int:
        with self._lock:
            self._reset_if_needed()
            return self._used

    def _reset_if_needed(self) -> None:
        today = self._today()
        if today != self._day:
            self._day = today
            self._used = 0

    def _today(self) -> date:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return now.astimezone(UTC).date()

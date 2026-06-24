from __future__ import annotations

from typing import Protocol


class ExternalContentProvider(Protocol):
    def fetch(self, url: str) -> str | None: ...


class NoExternalContentProvider:
    def fetch(self, _url: str) -> str | None:
        return None

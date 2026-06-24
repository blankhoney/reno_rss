from __future__ import annotations

import base64
from dataclasses import dataclass
import os

import httpx


@dataclass(frozen=True)
class MinifluxConfig:
    base_url: str
    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> MinifluxConfig:
        api_key = _usable_secret(os.environ.get("MINIFLUX_API_KEY"))
        return cls(
            base_url=os.environ.get("MINIFLUX_API_BASE_URL", "http://miniflux:8080"),
            api_key=api_key,
            username=os.environ.get("MINIFLUX_USERNAME"),
            password=os.environ.get("MINIFLUX_PASSWORD"),
            timeout_seconds=float(os.environ.get("MINIFLUX_TIMEOUT_SECONDS", "30")),
        )

    def auth_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"X-Auth-Token": self.api_key}
        if self.username and self.password:
            encoded = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode(
                "ascii"
            )
            return {"Authorization": f"Basic {encoded}"}
        raise RuntimeError("MINIFLUX_API_KEY or MINIFLUX_USERNAME/MINIFLUX_PASSWORD is required")


class MinifluxClient:
    def __init__(self, config: MinifluxConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")

    def list_entries(self, *, limit: int, after_entry_id: int | None = None) -> list[dict[str, object]]:
        params: dict[str, object] = {
            "limit": limit,
            "order": "published_at",
            "direction": "desc",
        }
        if after_entry_id is not None:
            params["after_entry_id"] = after_entry_id

        with httpx.Client(
            headers=self._config.auth_headers(),
            timeout=self._config.timeout_seconds,
        ) as client:
            response = client.get(f"{self._base_url}/v1/entries", params=params)
            response.raise_for_status()
            payload = response.json()
        entries = payload.get("entries", [])
        if not isinstance(entries, list):
            raise TypeError("Miniflux entries response must contain an entries list")
        return [_sync_entry_from_miniflux(entry) for entry in entries]


def _sync_entry_from_miniflux(entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise TypeError("Miniflux entry must be a mapping")
    feed = entry.get("feed") if isinstance(entry.get("feed"), dict) else {}
    feed_id = entry.get("feed_id", feed.get("id"))
    content = entry.get("content")
    result: dict[str, object] = {
        "feed_id": int(feed_id),
        "miniflux_entry_id": int(entry["id"]),
        "url": str(entry["url"]),
        "title": str(entry["title"]),
    }
    _copy_optional(entry, result, "published_at")
    _copy_optional(entry, result, "author")
    if content:
        result["content_html"] = str(content)
    return result


def _copy_optional(source: dict[str, object], destination: dict[str, object], key: str) -> None:
    value = source.get(key)
    if value is not None:
        destination[key] = value


def _usable_secret(value: str | None) -> str | None:
    if value is None or value.strip() == "" or value.strip() == "change_me":
        return None
    return value

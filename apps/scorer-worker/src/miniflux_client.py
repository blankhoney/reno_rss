"""
Miniflux API client using httpx.

Fetches recent unread entries for scoring.
"""

from __future__ import annotations

import httpx


class MinifluxClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (username, password)

    def get_recent_entries(self, limit: int = 100, status: str = "unread") -> list[dict]:
        """Return a list of entry dicts from the Miniflux API."""
        url = f"{self._base_url}/v1/entries"
        params = {"limit": limit, "status": status, "order": "published_at", "direction": "desc"}
        with httpx.Client(auth=self._auth, timeout=30) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("entries", [])

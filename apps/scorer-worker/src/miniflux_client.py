"""
Miniflux API client using httpx.

Fetches recent entries for scoring.
"""

from __future__ import annotations

import httpx


def entry_query_params(limit: int, status: str) -> dict:
    params = {"limit": limit, "order": "published_at", "direction": "desc"}
    if status != "all":
        params["status"] = status
    return params


class MinifluxClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (username, password)

    def get_recent_entries(self, limit: int = 300, status: str = "all") -> list[dict]:
        """Return a list of entry dicts from the Miniflux API."""
        url = f"{self._base_url}/v1/entries"
        params = entry_query_params(limit, status)
        with httpx.Client(auth=self._auth, timeout=30) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("entries", [])

    def get_entry(self, entry_id: int) -> dict | None:
        """Return one Miniflux entry dict, or None when it does not exist."""
        url = f"{self._base_url}/v1/entries/{entry_id}"
        with httpx.Client(auth=self._auth, timeout=30) as client:
            resp = client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

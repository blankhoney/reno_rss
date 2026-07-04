import base64

import httpx

from app.providers.miniflux import MinifluxClient, MinifluxConfig, _sync_entry_from_miniflux


def test_miniflux_auth_prefers_api_key():
    config = MinifluxConfig(
        base_url="https://miniflux.test",
        api_key="token-123",
        username="user",
        password="password",
    )

    assert config.auth_headers() == {"X-Auth-Token": "token-123"}


def test_miniflux_auth_falls_back_to_basic_auth():
    config = MinifluxConfig(
        base_url="https://miniflux.test",
        api_key=None,
        username="user",
        password="password",
    )

    expected = base64.b64encode(b"user:password").decode("ascii")
    assert config.auth_headers() == {"Authorization": f"Basic {expected}"}


def test_miniflux_entry_mapping_preserves_feed_metadata_for_local_fk_resolution():
    entry = _sync_entry_from_miniflux(
        {
            "id": 101,
            "title": "Entry title",
            "url": "https://example.com/post",
            "published_at": "2026-06-24T12:00:00Z",
            "feed": {
                "id": 31,
                "feed_url": "https://example.com/feed.xml",
                "site_url": "https://example.com",
                "title": "Example Feed",
                "category": {"id": 9},
            },
        }
    )

    assert entry["feed_id"] == 31
    assert entry["feed_url"] == "https://example.com/feed.xml"
    assert entry["feed_title"] == "Example Feed"
    assert entry["feed_site_url"] == "https://example.com"
    assert entry["miniflux_category_id"] == 9


def test_miniflux_client_reuses_one_http_client_until_disposed(monkeypatch):
    class RecordingHttpClient:
        instances: list["RecordingHttpClient"] = []

        def __init__(self, *, headers: dict[str, str], timeout: float) -> None:
            self.headers = headers
            self.timeout = timeout
            self.requests: list[tuple[str, dict[str, object] | None]] = []
            self.close_count = 0
            RecordingHttpClient.instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

        def get(self, url: str, *, params: dict[str, object] | None = None):
            self.requests.append((url, dict(params or {})))
            if url.endswith("/v1/entries"):
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    json={
                        "entries": [
                            {
                                "id": 101,
                                "title": "Entry title",
                                "url": "https://example.com/post",
                                "feed": {"id": 31},
                            }
                        ]
                    },
                    headers={"content-type": "application/json"},
                )
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={"content": "<article>full content</article>"},
                headers={"content-type": "application/json"},
            )

        def close(self) -> None:
            self.close_count += 1

    monkeypatch.setattr("app.providers.miniflux.httpx.Client", RecordingHttpClient)
    config = MinifluxConfig(
        base_url="https://miniflux.test/",
        api_key="token-123",
        timeout_seconds=9.5,
    )

    client = MinifluxClient(config)
    entries = client.list_entries(limit=5, after_entry_id=42)
    content = client.fetch_content(101)

    assert entries[0]["miniflux_entry_id"] == 101
    assert content == "<article>full content</article>"
    assert len(RecordingHttpClient.instances) == 1
    http_client = RecordingHttpClient.instances[0]
    assert http_client.headers == {"X-Auth-Token": "token-123"}
    assert http_client.timeout == 9.5
    assert http_client.close_count == 0
    assert http_client.requests == [
        (
            "https://miniflux.test/v1/entries",
            {"limit": 5, "order": "published_at", "direction": "desc", "after_entry_id": 42},
        ),
        (
            "https://miniflux.test/v1/entries/101/fetch-content",
            {"update_content": "true"},
        ),
    ]

    client.dispose()
    client.dispose()

    assert http_client.close_count == 1

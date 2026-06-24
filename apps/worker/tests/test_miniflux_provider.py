import base64

from app.providers.miniflux import MinifluxConfig, _sync_entry_from_miniflux


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

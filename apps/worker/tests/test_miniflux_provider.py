import base64

from app.providers.miniflux import MinifluxConfig


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

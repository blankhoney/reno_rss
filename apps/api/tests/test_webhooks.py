from app.domain.webhooks import build_webhook_envelope, deliver_webhook, sign_payload


def test_sign_payload_is_stable_hmac():
    body = b'{"event":"daily_brief"}'
    first = sign_payload("s3cret", body)
    second = sign_payload("s3cret", body)
    assert first == second
    assert first.startswith("sha256=")
    assert sign_payload("other", body) != first


def test_build_webhook_envelope_shape():
    envelope = build_webhook_envelope("high_score", {"article_id": 1, "score": 90})
    assert envelope["event"] == "high_score"
    assert envelope["payload"]["article_id"] == 1
    assert "generated_at" in envelope


class _FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeOpener:
    def __init__(self, status: int = 204):
        self.status = status
        self.last_request = None

    def open(self, req, timeout=5.0):
        self.last_request = req
        return _FakeResponse(self.status)


def test_deliver_webhook_posts_signed_json():
    opener = _FakeOpener(204)
    result = deliver_webhook(
        "https://example.test/hooks/ai-reader",
        "daily_brief",
        {"title": "今日情报"},
        secret="hook-secret",
        opener=opener,
    )
    assert result.ok is True
    assert result.status_code == 204
    assert opener.last_request is not None
    assert opener.last_request.data is not None
    assert b"daily_brief" in opener.last_request.data
    # urllib stores headers with title-case keys depending on version
    header_blob = " ".join(
        f"{key}:{value}" for key, value in opener.last_request.header_items()
    ).lower()
    assert "x-ai-reader-event" in header_blob or "event" in header_blob
    assert "signature" in header_blob


def test_deliver_webhook_empty_url_fails_soft():
    result = deliver_webhook("", "daily_brief", {})
    assert result.ok is False
    assert result.error == "empty_url"

import json

from app.webhooks import WebhookClient, sign_payload


class FakeResponse:
    status = 204

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class RecordingOpener:
    def __init__(self) -> None:
        self.request = None

    def open(self, request, timeout):
        assert timeout == 5.0
        self.request = request
        return FakeResponse()


def test_webhook_client_posts_signed_envelope():
    opener = RecordingOpener()
    client = WebhookClient(
        "https://example.test/hooks/reader",
        secret="hook-secret",
        opener=opener,
    )

    result = client.emit("high_score", {"article_id": 7, "base_score": 92})

    assert result == {
        "ok": True,
        "event": "high_score",
        "status_code": 204,
        "error": None,
    }
    assert opener.request is not None
    body = opener.request.data
    envelope = json.loads(body)
    assert envelope["event"] == "high_score"
    assert envelope["payload"]["article_id"] == 7
    headers = {key.lower(): value for key, value in opener.request.header_items()}
    assert headers["x-ai-reader-signature"] == sign_payload("hook-secret", body)


def test_webhook_client_returns_network_failure_without_raising():
    class FailingOpener:
        def open(self, _request, _timeout):
            raise TimeoutError("timed out")

    client = WebhookClient("https://example.test/hooks/reader", opener=FailingOpener())

    result = client.emit("daily_brief", {"item_count": 3})

    assert result["ok"] is False
    assert result["status_code"] is None
    assert result["error"] == "timed out"

import importlib
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _load_main(monkeypatch, entry_limit="300", entry_status="all"):
    monkeypatch.setenv("MINIFLUX_API_BASE_URL", "http://miniflux:8080")
    monkeypatch.setenv("MINIFLUX_USERNAME", "testuser")
    monkeypatch.setenv("MINIFLUX_PASSWORD", "testpass")
    monkeypatch.setenv("SCORING_DATABASE_URL", "postgres://scoring:test@postgres:5432/scoring")
    monkeypatch.setenv("SCORER_ENTRY_LIMIT", entry_limit)
    monkeypatch.setenv("SCORER_ENTRY_STATUS", entry_status)
    monkeypatch.setenv("SCORER_TENANT_ID", "default")
    monkeypatch.setenv("DIGEST_MIN_SCORE", "70")
    monkeypatch.setenv("DIGEST_MAX_ITEMS", "2")
    import main

    return importlib.reload(main)


def test_run_once_creates_digest_from_high_scores(monkeypatch):
    main = _load_main(monkeypatch)
    conn = MagicMock()
    entries = [
        {"id": 1, "feed_id": 1, "title": "Top", "url": "https://example.com/1", "content": "a"},
        {"id": 2, "feed_id": 1, "title": "Low", "url": "https://example.com/2", "content": "b"},
        {"id": 3, "feed_id": 1, "title": "Also Top", "url": "https://example.com/3", "content": "c"},
    ]

    monkeypatch.setattr(
        main.MinifluxClient,
        "get_recent_entries",
        lambda self, limit, status: entries,
    )
    monkeypatch.setattr(
        main,
        "score_entry",
        lambda entry: {
            "score": {1: 90, 2: 20, 3: 80}[entry["id"]],
            "tags": [],
            "reason": f"reason {entry['id']}",
            "model_version": "minimax:MiniMax-M2.7:rss-score-v1",
            "model_provider": "minimax",
            "model_name": "MiniMax-M2.7",
            "prompt_version": "rss-score-v1",
            "confidence": 0.8,
            "scoring_status": "success",
            "error_message": None,
        },
    )
    create_digest = MagicMock(return_value=55)
    upsert_digest_item = MagicMock()
    monkeypatch.setattr(main, "create_digest", create_digest)
    monkeypatch.setattr(main, "upsert_digest_item", upsert_digest_item)

    main.run_once(conn)

    create_digest.assert_called_once()
    assert upsert_digest_item.call_count == 2
    first_item = upsert_digest_item.call_args_list[0].args[1]
    second_item = upsert_digest_item.call_args_list[1].args[1]
    assert first_item["miniflux_entry_id"] == 1
    assert first_item["rank"] == 1
    assert second_item["miniflux_entry_id"] == 3
    assert second_item["rank"] == 2


def test_run_once_uses_configured_entry_window(monkeypatch):
    main = _load_main(monkeypatch, entry_limit="300", entry_status="all")
    conn = MagicMock()
    captured = {}

    def fake_get_recent_entries(self, limit, status):
        captured["limit"] = limit
        captured["status"] = status
        return []

    monkeypatch.setattr(main.MinifluxClient, "get_recent_entries", fake_get_recent_entries)

    main.run_once(conn)

    assert captured == {"limit": 300, "status": "all"}

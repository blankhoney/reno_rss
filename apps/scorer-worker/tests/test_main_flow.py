import importlib
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _load_main(monkeypatch):
    monkeypatch.setenv("MINIFLUX_API_BASE_URL", "http://miniflux:8080")
    monkeypatch.setenv("MINIFLUX_USERNAME", "testuser")
    monkeypatch.setenv("MINIFLUX_PASSWORD", "testpass")
    monkeypatch.setenv("SCORING_DATABASE_URL", "postgres://scoring:test@postgres:5432/scoring")
    monkeypatch.setenv("SCORER_TENANT_ID", "default")
    monkeypatch.setenv("SCORER_WEBHOOK_USERNAME", "scorer")
    monkeypatch.setenv("SCORER_WEBHOOK_PASSWORD", "secret")
    monkeypatch.setenv("SCORER_WEBHOOK_MAX_ENTRIES", "20")
    import main

    return importlib.reload(main)


def test_score_entry_by_id_fetches_and_persists_score(monkeypatch):
    main = _load_main(monkeypatch)
    conn = MagicMock()
    entry = {"id": 1, "feed_id": 1, "title": "Top", "url": "https://example.com/1", "content": "a"}

    monkeypatch.setattr(
        main.MinifluxClient,
        "get_entry",
        lambda self, entry_id: entry if entry_id == 1 else None,
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
    upsert_snapshot = MagicMock()
    upsert_score = MagicMock()
    monkeypatch.setattr(main, "upsert_snapshot", upsert_snapshot)
    monkeypatch.setattr(main, "upsert_score", upsert_score)
    monkeypatch.setattr(main, "get_latest_score", MagicMock(return_value=None))

    result = main.score_entry_by_id(conn, 1, force=True)

    assert result == {"ok": True, "entryId": 1, "score": 90, "cached": False}
    upsert_snapshot.assert_called_once()
    upsert_score.assert_called_once()


def test_score_entry_by_id_reuses_cached_score_without_force(monkeypatch):
    main = _load_main(monkeypatch)
    conn = MagicMock()
    entry = {"id": 1, "feed_id": 1, "title": "Top", "url": "https://example.com/1", "content": "a"}

    monkeypatch.setattr(main.MinifluxClient, "get_entry", lambda self, entry_id: entry)
    monkeypatch.setattr(main, "upsert_snapshot", MagicMock())
    monkeypatch.setattr(main, "get_latest_score", MagicMock(return_value={"score": 77}))
    score_entry = MagicMock()
    monkeypatch.setattr(main, "score_entry", score_entry)

    result = main.score_entry_by_id(conn, 1, force=False)

    assert result == {"ok": True, "entryId": 1, "score": 77, "cached": True}
    score_entry.assert_not_called()


def test_handle_miniflux_webhook_scores_only_unread_entries_with_limit(monkeypatch):
    main = _load_main(monkeypatch)
    conn = MagicMock()
    score_entry_by_id = MagicMock(return_value={"ok": True, "entryId": 1, "score": 80, "cached": False})
    monkeypatch.setattr(main, "score_entry_by_id", score_entry_by_id)
    monkeypatch.setattr(
        main,
        "get_scoring_settings",
        MagicMock(
            return_value={
                "auto_score_new_unread": True,
                "webhook_max_entries": 1,
                "manual_rescore_enabled": True,
            },
        ),
    )

    result = main.handle_miniflux_webhook(
        conn,
        "new_entries",
        {
            "entries": [
                {"id": 1, "status": "unread"},
                {"id": 2, "status": "read"},
                {"id": 3, "status": "unread"},
            ],
        },
    )

    assert result == {"ok": True, "eventType": "new_entries", "processed": 1, "skipped": 2}
    score_entry_by_id.assert_called_once_with(conn, 1, force=False)


def test_check_basic_auth_accepts_expected_credentials(monkeypatch):
    main = _load_main(monkeypatch)
    header = "Basic " + __import__("base64").b64encode(b"scorer:secret").decode()

    assert main.check_basic_auth(header, "scorer", "secret") is True
    assert main.check_basic_auth(header, "scorer", "wrong") is False

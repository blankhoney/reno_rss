"""
Task 5 — repository tests using mock DB connection.

We mock psycopg2 so these tests run without a live Postgres instance.
The key invariant tested: ON CONFLICT upsert path is triggered correctly
and conn.commit() is always called.
"""

import sys
import os
import json
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from repository import create_digest, upsert_digest_item, upsert_score, upsert_snapshot  # noqa: E402


def _make_conn():
    """Return a mock connection whose cursor is a context-manager mock."""
    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_cur)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_ctx
    return mock_conn, mock_cur


# ---------------------------------------------------------------------------
# upsert_snapshot tests
# ---------------------------------------------------------------------------

def test_upsert_snapshot_calls_execute_and_commit():
    conn, cur = _make_conn()
    row = {
        "tenant_id": "default",
        "miniflux_entry_id": 42,
        "feed_id": 7,
        "title": "Test Title",
        "url": "https://example.com",
        "published_at": "2026-05-11T00:00:00Z",
        "content_hash": "abc123",
    }
    upsert_snapshot(conn, row)
    cur.execute.assert_called_once()
    conn.commit.assert_called_once()


def test_upsert_snapshot_sql_contains_on_conflict():
    conn, cur = _make_conn()
    row = {
        "tenant_id": "t",
        "miniflux_entry_id": 1,
        "feed_id": None,
        "title": None,
        "url": None,
        "published_at": None,
        "content_hash": "h",
    }
    upsert_snapshot(conn, row)
    sql_called = cur.execute.call_args[0][0]
    assert "ON CONFLICT" in sql_called
    assert "DO UPDATE" in sql_called


# ---------------------------------------------------------------------------
# upsert_score tests
# ---------------------------------------------------------------------------

def test_upsert_score_calls_execute_and_commit():
    conn, cur = _make_conn()
    row = {
        "tenant_id": "default",
        "miniflux_entry_id": 42,
        "content_hash": "abc123",
        "score": 55,
        "tags": ["tech", "ai"],
        "reason": "length=200",
        "model_version": "0.1.0",
        "model_provider": "baseline",
        "model_name": "length-baseline",
        "prompt_version": "none",
        "confidence": 0.4,
        "scoring_status": "success",
        "error_message": None,
    }
    upsert_score(conn, row)
    cur.execute.assert_called_once()
    conn.commit.assert_called_once()


def test_upsert_score_serializes_tags_to_json():
    conn, cur = _make_conn()
    row = {
        "tenant_id": "t",
        "miniflux_entry_id": 1,
        "content_hash": "h",
        "score": 10,
        "tags": ["a", "b"],
        "reason": "r",
        "model_version": "0.1.0",
        "model_provider": "baseline",
        "model_name": "length-baseline",
        "prompt_version": "none",
        "confidence": 0.1,
        "scoring_status": "success",
        "error_message": None,
    }
    upsert_score(conn, row)
    _, kwargs_row = cur.execute.call_args[0]
    # tags should be JSON string, not a list
    assert isinstance(kwargs_row["tags"], str)
    parsed = json.loads(kwargs_row["tags"])
    assert parsed == ["a", "b"]


def test_upsert_score_sql_contains_on_conflict():
    conn, cur = _make_conn()
    row = {
        "tenant_id": "t",
        "miniflux_entry_id": 1,
        "content_hash": "h",
        "score": 0,
        "tags": [],
        "reason": "empty",
        "model_version": "0.1.0",
        "model_provider": "baseline",
        "model_name": "length-baseline",
        "prompt_version": "none",
        "confidence": 0.0,
        "scoring_status": "error",
        "error_message": "test",
    }
    upsert_score(conn, row)
    sql_called = cur.execute.call_args[0][0]
    assert "ON CONFLICT" in sql_called
    assert "DO UPDATE SET" in sql_called


def test_upsert_score_idempotent_called_twice():
    """Calling upsert_score twice for same entry should call execute twice (DB handles conflict)."""
    conn, cur = _make_conn()
    row = {
        "tenant_id": "t",
        "miniflux_entry_id": 99,
        "content_hash": "same_hash",
        "score": 30,
        "tags": [],
        "reason": "x",
        "model_version": "0.1.0",
        "model_provider": "baseline",
        "model_name": "length-baseline",
        "prompt_version": "none",
        "confidence": 0.3,
        "scoring_status": "success",
        "error_message": None,
    }
    upsert_score(conn, row)
    upsert_score(conn, row)
    assert cur.execute.call_count == 2
    assert conn.commit.call_count == 2


# ---------------------------------------------------------------------------
# digest tests
# ---------------------------------------------------------------------------
def test_create_digest_uses_on_conflict_and_returns_id():
    conn, cur = _make_conn()
    cur.fetchone.return_value = (123,)
    row = {
        "tenant_id": "default",
        "window_start": "2026-05-12T00:00:00Z",
        "window_end": "2026-05-12T01:00:00Z",
        "title": "Top RSS items",
        "summary": "2 items selected",
        "model_provider": "minimax",
        "model_name": "MiniMax-M2.7",
        "model_version": "minimax:MiniMax-M2.7:rss-score-v1",
        "prompt_version": "rss-score-v1",
        "status": "success",
    }

    digest_id = create_digest(conn, row)

    assert digest_id == 123
    sql_called = cur.execute.call_args[0][0]
    assert "ON CONFLICT" in sql_called
    assert "DO UPDATE SET" in sql_called
    assert "RETURNING id" in sql_called
    conn.commit.assert_called_once()


def test_upsert_digest_item_uses_on_conflict():
    conn, cur = _make_conn()
    row = {
        "digest_id": 123,
        "tenant_id": "default",
        "miniflux_entry_id": 42,
        "rank": 1,
        "score": 91,
        "title": "Important",
        "url": "https://example.com/item",
        "reason": "High signal.",
    }

    upsert_digest_item(conn, row)

    sql_called = cur.execute.call_args[0][0]
    assert "ON CONFLICT" in sql_called
    assert "DO UPDATE SET" in sql_called
    conn.commit.assert_called_once()

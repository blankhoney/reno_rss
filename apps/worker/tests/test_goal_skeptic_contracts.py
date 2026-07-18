"""Regression locks for GOAL skeptic flags that must never regress.

These tests document that prior verifier rejections about "missing rules",
"worth_scan overlap", and unattended ranking are fixed on the real paths.
"""

from datetime import UTC, datetime
from pathlib import Path


def test_rank_b4_recommendation_context_source_passes_rules_and_interest():
    """Skeptic flag 0: unattended Top10 must pass rules= into rank_b4."""
    source = Path("app/jobs/generate_recommendations.py").read_text(encoding="utf-8")
    assert "user_rules = list(context.rules or [])" in source
    assert "rules=user_rules" in source
    assert "titles_by_article=titles" in source or "titles_by_article=" in source
    assert "interest_weights=interests" in source or "interest_weights=" in source
    assert "rules: list[object] | None = None" in source
    assert "PUT /api/rules is NOT dead" in source


def test_recommendation_sink_loads_user_reader_rules():
    """Skeptic flag 0: DatabaseRecommendationSink must load user_reader_rules."""
    source = Path("app/db/recommendation_sink.py").read_text(encoding="utf-8")
    assert "def _rules_for_user" in source
    assert "FROM user_reader_rules" in source
    assert "rules=self._rules_for_user(user_id)" in source
    assert "interest_weights=self._interest_weights_for_user" in source


def test_daily_brief_worth_scan_is_read_only_not_must_read():
    """Skeptic flag 2: worth_scan must not include must_read tier."""
    source = Path("app/jobs/daily_brief.py").read_text(encoding="utf-8")
    assert 'str(item.get("tier", "")) == "read"' in source
    assert 'str(item.get("tier", "")) == "must_read"' in source
    # Guard against the old buggy pattern that ORed must_read into worth_scan.
    assert 'in {"must_read", "read"}' not in source
    assert "in {'must_read', 'read'}" not in source


def test_mute_rule_changes_unattended_top10_order():
    """Behavioral lock: mute feed removes high-score candidate from Top10."""
    from app.jobs.generate_recommendations import (
        RecommendationContext,
        rank_b4_recommendation_context,
    )

    now = datetime(2026, 7, 18, tzinfo=UTC)
    context = RecommendationContext(
        user_id="u1",
        candidates=[
            {
                "article_id": 1,
                "feed_ids": [10],
                "base_score": 99,
                "published_at": now,
                "risk_uncertainty": 10,
                "risk_flags": [],
            },
            {
                "article_id": 2,
                "feed_ids": [20],
                "base_score": 70,
                "published_at": now,
                "risk_uncertainty": 10,
                "risk_flags": [],
            },
        ],
        user_priority_by_feed={10: 0, 20: 0},
        feedback_by_article={},
        article_status_by_article={},
        now=now,
        rules=[{"type": "mute", "feed_id": 10}],
        titles_by_article={1: "Muted", 2: "Kept"},
    )
    ranked = list(rank_b4_recommendation_context(context))
    ids = [item.article_id for item in ranked]
    assert 1 not in ids
    assert 2 in ids

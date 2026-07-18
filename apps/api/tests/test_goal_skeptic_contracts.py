"""API-side locks for GOAL skeptic flags (rules/brief/interest/product surfaces)."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


def test_briefs_fallback_worth_scan_excludes_must_read():
    """Skeptic flag 2: fallback brief must keep tiers disjoint."""
    from app.api.routes.briefs import brief_from_recommendations

    edition = SimpleNamespace(
        generated_at=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
        items=[
            SimpleNamespace(article_id=1, rank=1, tier="must_read", rank_score=95.0, reason="hot"),
            SimpleNamespace(article_id=2, rank=2, tier="read", rank_score=72.0, reason="ok"),
            SimpleNamespace(article_id=3, rank=3, tier="skim", rank_score=40.0, reason="low"),
        ],
    )
    recommendation_repo = SimpleNamespace(latest_for_user=lambda _uid: edition)
    article_repo = SimpleNamespace(
        get_articles=lambda ids: {
            1: SimpleNamespace(title="Must"),
            2: SimpleNamespace(title="Read"),
            3: SimpleNamespace(title="Skim"),
        }
    )
    scoring_repo = SimpleNamespace(
        active_scores_for_articles=lambda ids: {
            1: SimpleNamespace(base_score=95, summary_zh="a"),
            2: SimpleNamespace(base_score=72, summary_zh="b"),
            3: SimpleNamespace(base_score=40, summary_zh="c"),
        }
    )
    brief = brief_from_recommendations(uuid4(), recommendation_repo, article_repo, scoring_repo)
    assert brief is not None
    must_ids = {row["article_id"] for row in brief["must_read"]}
    worth_ids = {row["article_id"] for row in brief["worth_scan"]}
    assert must_ids == {1}
    assert worth_ids == {2}
    assert must_ids.isdisjoint(worth_ids)


def test_interest_routes_exist_in_main_router():
    """Skeptic flag 4: personalization surfaces must be mounted."""
    main_src = Path("app/main.py").read_text(encoding="utf-8")
    assert "interest" in main_src
    assert Path("app/api/routes/interest.py").exists()
    assert Path("app/domain/personalization.py").exists()


def test_product_api_routes_exist_for_goal_modules():
    """Skeptic flag 3: clusters/rules/themes/saved-searches/research exist as routes."""
    routes = Path("app/api/routes")
    for name in ("clusters.py", "rules.py", "themes.py", "saved_searches.py", "research.py", "interest.py"):
        assert (routes / name).exists(), name


def test_export_zip_and_annotation_search_exist():
    """Skeptic flag 5: zip export + annotation search endpoints present."""
    src = Path("app/api/routes/articles.py").read_text(encoding="utf-8")
    assert 'pattern="^(markdown|json|zip)$"' in src
    assert 'format == "zip"' in src
    assert '@router.get("/annotations/search")' in src


def test_rank_b4_accepts_and_applies_rules_kwarg():
    """Skeptic flag 0 (API ranking domain): mute rule filters candidates."""
    from app.domain.ranking import Candidate, rank_b4
    from app.domain.rules import Rule

    ranked = rank_b4(
        user_priority_by_feed={1: 0, 2: 0},
        candidates=[
            Candidate(
                article_id=1,
                feed_ids=[1],
                base_score=99,
                published_at=datetime(2026, 7, 17, tzinfo=UTC),
            ),
            Candidate(
                article_id=2,
                feed_ids=[2],
                base_score=70,
                published_at=datetime(2026, 7, 17, tzinfo=UTC),
            ),
        ],
        feedback_by_article={},
        now=datetime(2026, 7, 18, tzinfo=UTC),
        rules=[Rule(type="mute", feed_id=1)],
        titles_by_article={1: "Muted", 2: "Kept"},
    )
    assert [item.article_id for item in ranked] == [2]


@pytest.mark.asyncio
async def test_interest_api_roundtrip(client):
    """Skeptic flag 4 behavioral: get/reset/export interest works."""
    await client.post("/api/auth/login", json={"display_name": "SkepticUser"})
    got = await client.get("/api/me/interest")
    assert got.status_code == 200
    assert "keywords" in got.json()
    reset = await client.post("/api/me/interest/reset")
    assert reset.status_code == 200
    export = await client.get("/api/me/interest/export")
    assert export.status_code == 200
    assert export.json()["format"] == "interest_vector.v1"

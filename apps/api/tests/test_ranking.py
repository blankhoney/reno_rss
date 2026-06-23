from datetime import UTC, datetime

import pytest


def test_b4_tie_breaks_by_score_published_at_and_id():
    from app.domain.ranking import Candidate, rank_b4

    ranked = rank_b4(
        user_priority_by_feed={1: 0},
        candidates=[
            Candidate(
                article_id=1,
                feed_ids=[1],
                base_score=80,
                published_at=datetime(2026, 6, 20, tzinfo=UTC),
                risk_uncertainty=20,
            ),
            Candidate(
                article_id=2,
                feed_ids=[1],
                base_score=80,
                published_at=datetime(2026, 6, 21, tzinfo=UTC),
                risk_uncertainty=20,
            ),
        ],
        feedback_by_article={},
        now=datetime(2026, 6, 22, tzinfo=UTC),
    )

    assert [item.article_id for item in ranked] == [2, 1]


def test_deduped_article_with_any_subscribed_source_is_not_exploration():
    from app.domain.ranking import Candidate, rank_b4

    ranked = rank_b4(
        user_priority_by_feed={10: 0},
        candidates=[
            Candidate(
                article_id=1,
                feed_ids=[10, 20],
                base_score=90,
                published_at=datetime(2026, 6, 21, tzinfo=UTC),
                risk_uncertainty=20,
            ),
        ],
        feedback_by_article={},
        now=datetime(2026, 6, 22, tzinfo=UTC),
    )

    assert ranked[0].source == "subscription"


def test_b4_merges_duplicate_article_sources_before_classification():
    from app.domain.ranking import Candidate, rank_b4

    ranked = rank_b4(
        user_priority_by_feed={10: 0},
        candidates=[
            Candidate(
                article_id=1,
                feed_ids=[20],
                base_score=90,
                published_at=datetime(2026, 6, 21, tzinfo=UTC),
                risk_uncertainty=20,
            ),
            Candidate(
                article_id=1,
                feed_ids=[10],
                base_score=90,
                published_at=datetime(2026, 6, 20, tzinfo=UTC),
                risk_uncertainty=20,
            ),
        ],
        feedback_by_article={},
        now=datetime(2026, 6, 22, tzinfo=UTC),
    )

    assert ranked[0].source == "subscription"


def test_b4_places_exploration_after_subscription_slots():
    from app.domain.ranking import Candidate, rank_b4

    ranked = rank_b4(
        user_priority_by_feed={1: 0},
        candidates=[
            Candidate(
                article_id=1,
                feed_ids=[1],
                base_score=75,
                published_at=datetime(2026, 6, 21, tzinfo=UTC),
                risk_uncertainty=20,
            ),
            Candidate(
                article_id=2,
                feed_ids=[99],
                base_score=95,
                published_at=datetime(2026, 6, 21, tzinfo=UTC),
                risk_uncertainty=20,
            ),
        ],
        feedback_by_article={},
        now=datetime(2026, 6, 22, tzinfo=UTC),
    )

    assert [(item.article_id, item.rank, item.source) for item in ranked] == [
        (1, 1, "subscription"),
        (2, 2, "exploration"),
    ]


def test_b4_expands_candidate_window_to_14_days_when_recent_window_is_short():
    from app.domain.ranking import Candidate, rank_b4

    ranked = rank_b4(
        user_priority_by_feed={1: 0},
        candidates=[
            Candidate(
                article_id=1,
                feed_ids=[1],
                base_score=60,
                published_at=datetime(2026, 6, 20, tzinfo=UTC),
                risk_uncertainty=20,
            ),
            Candidate(
                article_id=2,
                feed_ids=[1],
                base_score=99,
                published_at=datetime(2026, 6, 1, tzinfo=UTC),
                risk_uncertainty=20,
            ),
        ],
        feedback_by_article={},
        now=datetime(2026, 6, 24, tzinfo=UTC),
    )

    assert [item.article_id for item in ranked] == [1]


def test_b4_uses_real_now_by_default_for_candidate_window():
    from app.domain.ranking import Candidate, rank_b4

    ranked = rank_b4(
        user_priority_by_feed={1: 0},
        candidates=[
            Candidate(
                article_id=1,
                feed_ids=[1],
                base_score=99,
                published_at=datetime(2020, 1, 1, tzinfo=UTC),
                risk_uncertainty=20,
            ),
        ],
        feedback_by_article={},
    )

    assert ranked == []


def test_b4_expands_window_after_duplicate_hard_filtering():
    from app.domain.ranking import Candidate, rank_b4

    candidates = [
        Candidate(
            article_id=article_id,
            feed_ids=[1],
            base_score=60,
            published_at=datetime(2026, 6, 23, tzinfo=UTC),
            risk_uncertainty=20,
            risk_flags=["duplicate"],
        )
        for article_id in range(1, 11)
    ]
    candidates.append(
        Candidate(
            article_id=99,
            feed_ids=[1],
            base_score=90,
            published_at=datetime(2026, 6, 18, tzinfo=UTC),
            risk_uncertainty=20,
        )
    )

    ranked = rank_b4(
        user_priority_by_feed={1: 0},
        candidates=candidates,
        feedback_by_article={},
        now=datetime(2026, 6, 24, tzinfo=UTC),
    )

    assert [item.article_id for item in ranked] == [99]


def test_b4_excludes_read_and_skipped_articles():
    from app.domain.ranking import Candidate, rank_b4

    ranked = rank_b4(
        user_priority_by_feed={1: 0},
        candidates=[
            Candidate(
                article_id=1,
                feed_ids=[1],
                base_score=99,
                published_at=datetime(2026, 6, 21, tzinfo=UTC),
                risk_uncertainty=20,
            ),
            Candidate(
                article_id=2,
                feed_ids=[1],
                base_score=98,
                published_at=datetime(2026, 6, 21, tzinfo=UTC),
                risk_uncertainty=20,
            ),
            Candidate(
                article_id=3,
                feed_ids=[1],
                base_score=70,
                published_at=datetime(2026, 6, 21, tzinfo=UTC),
                risk_uncertainty=20,
            ),
        ],
        feedback_by_article={},
        article_status_by_article={1: "read", 2: "skipped", 3: "unread"},
    )

    assert [item.article_id for item in ranked] == [3]


@pytest.mark.asyncio
async def test_latest_recommendations_requires_session(client):
    response = await client.get("/api/recommendations/latest")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_latest_recommendations_returns_current_user_edition(app, client):
    from app.domain.ranking import RankedItem

    login = await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Recommended",
            "published_at": datetime(2026, 6, 21, tzinfo=UTC),
        }
    )
    app.state.recommendation_repository.save_edition(
        user_id=login.json()["user"]["id"],
        items=[
            RankedItem(
                article_id=article.id,
                rank=1,
                rank_score=92.5,
                tier="must_read",
                reason="High score",
                source="subscription",
            )
        ],
        algorithm_version="b4.v1",
    )

    response = await client.get("/api/recommendations/latest")

    assert response.status_code == 200
    assert response.json()["edition"]["algorithm_version"] == "b4.v1"
    assert response.json()["items"][0]["rank"] == 1
    assert response.json()["items"][0]["article"]["id"] == article.id
    assert response.json()["items"][0]["rank_score"] == 92.5

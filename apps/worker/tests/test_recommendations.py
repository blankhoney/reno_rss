from dataclasses import dataclass

import pytest

from app.jobs.generate_recommendations import RecommendationContext, generate_recommendations


@dataclass(frozen=True)
class RankedItem:
    article_id: int
    rank: int
    rank_score: float
    tier: str
    reason: str
    source: str


class RecordingSink:
    def __init__(self, contexts_by_user, target_users=None):
        self.contexts_by_user = contexts_by_user
        self.target_users = target_users or []
        self.context_requests = []
        self.list_target_users_calls = 0
        self.saved_editions = []

    def recommendation_context_for_user(self, user_id):
        self.context_requests.append(user_id)
        return self.contexts_by_user[user_id]

    def list_target_users(self):
        self.list_target_users_calls += 1
        return list(self.target_users)

    def save_recommendation_edition(self, user_id, items, algorithm_version):
        self.saved_editions.append((user_id, list(items), algorithm_version))


def test_generate_recommendations_ranks_and_saves_one_edition_per_requested_user():
    sink = RecordingSink(
        {
            "user-1": RecommendationContext(
                user_id="user-1",
                candidates=[
                    {"article_id": 101, "score": 20},
                    {"article_id": 102, "score": 90},
                ],
                user_priority_by_feed={1: 10},
                feedback_by_article={},
                article_status_by_article={},
            ),
            "user-2": RecommendationContext(
                user_id="user-2",
                candidates=[
                    {"article_id": 201, "score": 65},
                    {"article_id": 202, "score": 40},
                ],
                user_priority_by_feed={2: -5},
                feedback_by_article={201: {"feedback_type": "underrated"}},
                article_status_by_article={202: "read"},
            ),
        }
    )
    ranker_calls = []

    def ranker(context):
        ranker_calls.append(context)
        return [
            RankedItem(
                article_id=item["article_id"],
                rank=index,
                rank_score=float(item["score"]),
                tier="read",
                reason="B4 deterministic ranking",
                source="subscription",
            )
            for index, item in enumerate(
                sorted(context.candidates, key=lambda item: item["score"], reverse=True),
                start=1,
            )
        ]

    result = generate_recommendations({"user_ids": ["user-1", "user-2"]}, sink, ranker)

    assert sink.context_requests == ["user-1", "user-2"]
    assert sink.list_target_users_calls == 0
    assert [context.user_id for context in ranker_calls] == ["user-1", "user-2"]
    assert ranker_calls[0].user_priority_by_feed == {1: 10}
    assert ranker_calls[1].feedback_by_article == {201: {"feedback_type": "underrated"}}
    assert ranker_calls[1].article_status_by_article == {202: "read"}
    assert sink.saved_editions == [
        (
            "user-1",
                [
                    {
                        "article_id": 102,
                        "rank": 1,
                        "rank_score": 90.0,
                        "tier": "read",
                        "reason": "B4 deterministic ranking",
                        "source": "subscription",
                    },
                    {
                        "article_id": 101,
                        "rank": 2,
                        "rank_score": 20.0,
                        "tier": "read",
                        "reason": "B4 deterministic ranking",
                        "source": "subscription",
                    },
                ],
                "b4.v1",
            ),
            (
                "user-2",
                [
                    {
                        "article_id": 201,
                        "rank": 1,
                        "rank_score": 65.0,
                        "tier": "read",
                        "reason": "B4 deterministic ranking",
                        "source": "subscription",
                    },
                    {
                        "article_id": 202,
                        "rank": 2,
                        "rank_score": 40.0,
                        "tier": "read",
                        "reason": "B4 deterministic ranking",
                        "source": "subscription",
                    },
                ],
                "b4.v1",
            ),
    ]
    assert result == {
        "algorithm_version": "b4.v1",
        "editions_saved": 2,
        "users_seen": 2,
    }


def test_generate_recommendations_uses_target_users_when_payload_omits_user_ids():
    sink = RecordingSink(
        {
            "user-3": RecommendationContext(
                user_id="user-3",
                candidates=[{"article_id": 301, "score": 10}],
                user_priority_by_feed={},
                feedback_by_article={},
                article_status_by_article={},
            )
        },
        target_users=["user-3"],
    )

    generate_recommendations({}, sink, lambda context: [])

    assert sink.list_target_users_calls == 1
    assert sink.context_requests == ["user-3"]


def test_generate_recommendations_saves_b4_algorithm_version_and_serialized_ranked_items():
    sink = RecordingSink(
        {
            "user-4": RecommendationContext(
                user_id="user-4",
                candidates=[{"article_id": 401, "score": 10}],
                user_priority_by_feed={},
                feedback_by_article={},
                article_status_by_article={},
            )
        }
    )
    ranked_items = [
        RankedItem(
            article_id=499,
            rank=1,
            rank_score=88.5,
            tier="must_read",
            reason="B4 deterministic ranking",
            source="subscription",
        )
    ]

    generate_recommendations({"user_ids": ["user-4"]}, sink, lambda _items: ranked_items)

    assert sink.saved_editions == [
        (
            "user-4",
            [
                {
                    "article_id": 499,
                    "rank": 1,
                    "rank_score": 88.5,
                    "tier": "must_read",
                    "reason": "B4 deterministic ranking",
                    "source": "subscription",
                }
            ],
            "b4.v1",
        )
    ]


def test_generate_recommendations_rejects_non_b4_algorithm_version():
    sink = RecordingSink({})

    with pytest.raises(ValueError, match="algorithm_version"):
        generate_recommendations({"algorithm_version": "b4.experiment"}, sink, lambda context: [])


def test_database_recommendation_sink_builds_context_and_writes_edition():
    from sqlalchemy import create_engine, text

    from app.db.recommendation_sink import DatabaseRecommendationSink
    from app.jobs.generate_recommendations import rank_b4_recommendation_context

    engine = create_engine("sqlite:///:memory:")
    _create_recommendation_schema(engine)
    sink = DatabaseRecommendationSink(engine=engine)

    result = generate_recommendations(
        {"user_ids": ["user-1"]},
        sink,
        rank_b4_recommendation_context,
    )

    with engine.begin() as connection:
        editions = connection.execute(text("SELECT * FROM recommendation_editions")).mappings().all()
        items = (
            connection.execute(text("SELECT * FROM recommendation_items ORDER BY rank"))
            .mappings()
            .all()
        )

    assert result["editions_saved"] == 1
    assert len(editions) == 1
    assert editions[0]["user_id"] == "user-1"
    assert [(item["article_id"], item["rank"], item["source"]) for item in items] == [
        (1, 1, "subscription"),
        (2, 2, "exploration"),
    ]


def _create_recommendation_schema(engine):
    from datetime import UTC, datetime
    import json

    from sqlalchemy import text

    now = datetime(2026, 6, 24, 12, tzinfo=UTC)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE app_users (id TEXT PRIMARY KEY, role TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE user_feed_subscriptions (
                user_id TEXT,
                feed_id INTEGER,
                enabled INTEGER,
                user_priority INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                published_at TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE article_sources (
                id INTEGER PRIMARY KEY,
                article_id INTEGER,
                feed_id INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE article_base_scores (
                id INTEGER PRIMARY KEY,
                article_id INTEGER,
                base_score INTEGER,
                recommendation_tier TEXT,
                reason TEXT,
                risk_flags TEXT,
                dimension_scores TEXT,
                scoring_status TEXT,
                is_active INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE user_article_states (
                user_id TEXT,
                article_id INTEGER,
                status TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE user_article_feedback_scores (
                user_id TEXT,
                article_id INTEGER,
                feedback_type TEXT,
                user_score INTEGER
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE recommendation_editions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                source_batch_id INTEGER,
                edition_type TEXT,
                algorithm_version TEXT,
                generated_at TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE recommendation_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                edition_id INTEGER,
                article_id INTEGER,
                rank INTEGER,
                rank_score REAL,
                tier TEXT,
                reason TEXT,
                source TEXT
            )
            """
        )
        connection.execute(text("INSERT INTO app_users (id, role) VALUES ('user-1', 'user')"))
        connection.execute(
            text(
                "INSERT INTO user_feed_subscriptions VALUES ('user-1', 10, 1, 5)"
            )
        )
        connection.execute(
            text("INSERT INTO articles (id, published_at) VALUES (1, :now), (2, :now)"),
            {"now": now.isoformat()},
        )
        connection.execute(
            text("INSERT INTO article_sources VALUES (1, 1, 10), (2, 2, 99)")
        )
        connection.execute(
            text(
                """
                INSERT INTO article_base_scores (
                    id, article_id, base_score, recommendation_tier, reason,
                    risk_flags, dimension_scores, scoring_status, is_active
                )
                VALUES
                  (1, 1, 85, 'must_read', 'subscribed', '[]', :dims, 'success', 1),
                  (2, 2, 82, 'read', 'explore', '[]', :dims, 'success', 1)
                """
            ),
            {"dims": json.dumps({"risk_uncertainty": 20})},
        )

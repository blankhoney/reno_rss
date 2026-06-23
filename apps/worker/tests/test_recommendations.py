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

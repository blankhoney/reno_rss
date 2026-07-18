from datetime import UTC, datetime

import pytest


def test_validate_rule_rejects_unknown_type():
    from app.domain.rules import validate_rule

    with pytest.raises(ValueError, match="unsupported rule type"):
        validate_rule({"type": "explode"})


def test_apply_rules_mutes_feed_and_keyword():
    from app.domain.rules import Rule, RuleArticle, apply_rules

    candidates = [
        RuleArticle(article_id=1, feed_ids=[10], title="Quiet news", score=80),
        RuleArticle(article_id=2, feed_ids=[20], title="Sponsored promo", score=90),
        RuleArticle(article_id=3, feed_ids=[30], title="Good read", score=70),
    ]
    result = apply_rules(
        candidates,
        [
            Rule(type="mute", feed_id=10),
            Rule(type="mute", keyword="sponsored"),
        ],
    )
    assert [item.article_id for item in result] == [3]


def test_apply_rules_score_threshold_filters():
    from app.domain.rules import Rule, RuleArticle, apply_rules

    result = apply_rules(
        [
            RuleArticle(article_id=1, feed_ids=[1], title="A", score=40),
            RuleArticle(article_id=2, feed_ids=[1], title="B", score=80),
        ],
        [Rule(type="score_threshold", weight=50)],
    )
    assert [item.article_id for item in result] == [2]


def test_apply_rules_boost_and_keyword_raise_score():
    from app.domain.rules import Rule, RuleArticle, apply_rules

    result = apply_rules(
        [
            RuleArticle(article_id=1, feed_ids=[5], title="Rust release notes", score=60),
            RuleArticle(article_id=2, feed_ids=[9], title="Other", score=60),
        ],
        [
            Rule(type="boost", feed_id=5, weight=15),
            Rule(type="keyword", keyword="rust", weight=5),
        ],
    )
    by_id = {item.article_id: item for item in result}
    assert by_id[1].score == 80  # 60 + 15 + 5
    assert by_id[2].score == 60


def test_rank_b4_optional_rules_mute_feed():
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
async def test_rules_require_session(client):
    get_response = await client.get("/api/rules")
    put_response = await client.put("/api/rules", json={"rules": []})
    assert get_response.status_code == 401
    assert put_response.status_code == 401


@pytest.mark.asyncio
async def test_rules_put_get_roundtrip(app, client):
    await client.post("/api/auth/login", json={"display_name": "RuleUser"})

    empty = await client.get("/api/rules")
    assert empty.status_code == 200
    assert empty.json() == {"rules": []}

    put = await client.put(
        "/api/rules",
        json={
            "rules": [
                {"type": "boost", "feed_id": 3, "weight": 12},
                {"type": "mute", "keyword": "sponsored"},
                {"type": "keyword", "keyword": "rust", "weight": 8},
                {"type": "score_threshold", "weight": 55},
            ]
        },
    )
    assert put.status_code == 200
    rules = put.json()["rules"]
    assert len(rules) == 4
    assert rules[0] == {"type": "boost", "feed_id": 3, "weight": 12.0}
    assert rules[1] == {"type": "mute", "keyword": "sponsored"}

    got = await client.get("/api/rules")
    assert got.status_code == 200
    assert got.json()["rules"] == put.json()["rules"]


@pytest.mark.asyncio
async def test_rules_put_rejects_invalid_rule(client):
    await client.post("/api/auth/login", json={"display_name": "BadRule"})
    response = await client.put(
        "/api/rules",
        json={"rules": [{"type": "mute"}]},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_rule"


def test_memory_rule_repository_isolates_users():
    from uuid import uuid4

    from app.db.repositories.rules import MemoryRuleRepository
    from app.domain.rules import Rule

    store = MemoryRuleRepository()
    user_a = uuid4()
    user_b = uuid4()
    store.put_rules(user_a, [Rule(type="boost", feed_id=1, weight=5)])
    assert store.get_rules(user_b) == []
    assert store.get_rules(user_a)[0].feed_id == 1

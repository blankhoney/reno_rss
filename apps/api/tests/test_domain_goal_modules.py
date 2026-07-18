from datetime import UTC, datetime, timedelta

from app.domain.citations import extract_citation_candidates
from app.domain.clusters import ClusterArticle, cluster_articles, title_similarity
from app.domain.rules import Rule, RuleArticle, apply_rules
from app.domain.spaced_review import (
    advance_review_schedule,
    initial_review_schedule,
    is_due,
)
from app.domain.themes import cluster_themes


def test_title_similarity_and_story_clusters():
    assert title_similarity("OpenAI launches model X", "OpenAI launches model X today") > 0.4
    articles = [
        ClusterArticle(1, "OpenAI launches model X", datetime(2026, 7, 18, tzinfo=UTC), 90),
        ClusterArticle(
            2, "OpenAI launches model X for enterprise", datetime(2026, 7, 18, tzinfo=UTC), 80
        ),
        ClusterArticle(3, "Unrelated cooking tips", datetime(2026, 7, 18, tzinfo=UTC), 10),
    ]
    clusters = cluster_articles(articles, min_similarity=0.3, min_cluster_size=2)
    assert clusters
    assert clusters[0].size >= 2
    assert clusters[0].main_article_id in {1, 2}


def test_apply_rules_mute_boost_keyword_threshold():
    candidates = [
        RuleArticle(1, [10], "Rust async runtime", 80),
        RuleArticle(2, [11], "Gossip blog", 40),
        RuleArticle(3, [12], "Keyword radar hit", 70),
    ]
    rules = [
        Rule("mute", feed_id=11),
        Rule("boost", feed_id=10, weight=15),
        Rule("keyword", keyword="radar", weight=5),
        Rule("score_threshold", weight=50),
    ]
    adjusted = apply_rules(candidates, rules)
    ids = {item.article_id: item for item in adjusted}
    assert 2 not in ids
    assert ids[1].score == 95
    assert ids[3].score == 75


def test_spaced_review_ladder():
    created = datetime(2026, 7, 1, tzinfo=UTC)
    state = initial_review_schedule(created)
    assert is_due(state.next_review_at, created_at=created, now=created)
    remembered = advance_review_schedule(
        interval_days=state.interval_days,
        review_count=state.review_count,
        remembered=True,
        now=created,
    )
    assert remembered.interval_days == 3
    assert remembered.next_review_at == created + timedelta(days=3)


def test_extract_citations_require_article_presence():
    article = "The system should ground answers in quotes from the source body carefully."
    answer = (
        '结论：可以。\n引用："ground answers in quotes from the source body"\n'
        '引用："not in article at all here!!!"'
    )
    cites = extract_citation_candidates(article, answer)
    assert len(cites) == 1
    assert "ground answers" in cites[0].quote


def test_theme_clusters_group_tags():
    themes = cluster_themes(
        [
            {"article_id": 1, "tags": ["ai", "rust"], "base_score": 80},
            {"article_id": 2, "tags": ["ai"], "base_score": 70},
            {"article_id": 3, "tags": ["cooking"], "base_score": 40},
        ],
        max_themes=10,
    )
    assert themes[0]["label"] == "ai"
    assert 1 in themes[0]["article_ids"] and 2 in themes[0]["article_ids"]

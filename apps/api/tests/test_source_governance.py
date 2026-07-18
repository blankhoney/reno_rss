from app.domain.source_governance import FeedQualitySample, decide_feed_demotions


def test_decide_feed_demotions_requires_min_samples():
    samples = [
        FeedQualitySample(feed_id=1, content_quality="snippet"),
        FeedQualitySample(feed_id=1, content_quality="failed"),
        FeedQualitySample(feed_id=1, content_quality="snippet"),
    ]
    assert decide_feed_demotions(samples, min_samples=5) == []


def test_decide_feed_demotions_flags_bad_ratio():
    samples = [
        FeedQualitySample(feed_id=9, content_quality="snippet"),
        FeedQualitySample(feed_id=9, content_quality="failed"),
        FeedQualitySample(feed_id=9, content_quality="blocked"),
        FeedQualitySample(feed_id=9, content_quality="snippet"),
        FeedQualitySample(feed_id=9, content_quality="full"),
        FeedQualitySample(feed_id=3, content_quality="full"),
        FeedQualitySample(feed_id=3, content_quality="full"),
        FeedQualitySample(feed_id=3, content_quality="full"),
        FeedQualitySample(feed_id=3, content_quality="full"),
        FeedQualitySample(feed_id=3, content_quality="full"),
    ]
    decisions = {item.feed_id: item for item in decide_feed_demotions(samples, min_samples=5)}
    assert decisions[9].demote is True
    assert decisions[9].bad_ratio >= 0.6
    assert decisions[3].demote is False

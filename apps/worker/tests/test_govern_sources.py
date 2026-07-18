from app.jobs.govern_sources import govern_sources


class FakeSink:
    def __init__(self):
        self.samples = [
            {"feed_id": 1, "content_quality": "snippet", "base_score": 20},
            {"feed_id": 1, "content_quality": "failed", "base_score": 10},
            {"feed_id": 1, "content_quality": "blocked", "base_score": 5},
            {"feed_id": 1, "content_quality": "snippet", "base_score": 15},
            {"feed_id": 1, "content_quality": "snippet", "base_score": 12},
            {"feed_id": 2, "content_quality": "full", "base_score": 80},
            {"feed_id": 2, "content_quality": "full", "base_score": 82},
            {"feed_id": 2, "content_quality": "full", "base_score": 79},
            {"feed_id": 2, "content_quality": "full", "base_score": 90},
            {"feed_id": 2, "content_quality": "full", "base_score": 88},
        ]
        self.demoted = []

    def list_recent_quality_samples(self, *, limit: int = 500):
        return list(self.samples)[:limit]

    def demote_feed(self, feed_id: int, *, reason: str) -> int:
        self.demoted.append((feed_id, reason))
        return 2


def test_govern_sources_demotes_bad_feed_only():
    sink = FakeSink()
    result = govern_sources({"min_samples": 5, "bad_ratio_threshold": 0.6}, sink)
    assert result["status"] == "ok"
    assert result["feeds_demoted"] == 1
    assert sink.demoted[0][0] == 1
    assert all(item[0] != 2 for item in sink.demoted)


def test_govern_sources_dry_run_does_not_write():
    sink = FakeSink()
    result = govern_sources(
        {"dry_run": True, "min_samples": 5, "bad_ratio_threshold": 0.6},
        sink,
    )
    assert result["dry_run"] is True
    assert result["feeds_demoted"] == 1
    assert sink.demoted == []

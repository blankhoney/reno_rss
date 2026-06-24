from datetime import UTC, datetime, timedelta

import pytest

from app.benchmark.ranking import BenchmarkArticle, BenchmarkDataset, BenchmarkUser, run_ranking_benchmark
from app.jobs.run_benchmark import BenchmarkRunRejected, run_benchmark


@pytest.fixture
def mini_dataset():
    now = datetime(2026, 6, 24, tzinfo=UTC)
    articles = []
    for index in range(20):
        article_id = index + 1
        high_value = article_id in {1, 2, 3, 4, 5, 6, 7, 8, 19, 20}
        articles.append(
            BenchmarkArticle(
                article_id=article_id,
                feed_ids=[1 if article_id <= 10 else 2],
                title=f"{'AI agent benchmark' if high_value else 'general update'} {article_id}",
                tags=["ai"] if high_value else ["misc"],
                base_score=95 - index if high_value else 45 + index,
                published_at=now - timedelta(hours=index),
                risk_uncertainty=20,
                risk_flags=[],
                weak_label="must_read" if high_value else "skip",
            )
        )
    return BenchmarkDataset(
        users=[
            BenchmarkUser(user_id="user-1", priority_by_feed={1: 10, 2: 0}),
            BenchmarkUser(user_id="user-2", priority_by_feed={1: 0, 2: 10}),
        ],
        articles=articles,
        generated_at=now,
    )


def test_mini_benchmark_runs_b0_to_b4_without_real_llm(mini_dataset):
    report = run_ranking_benchmark(mini_dataset, provider_name="mock")

    assert report.status == "succeeded"
    assert set(report.baselines) >= {"B0", "B1", "B2", "B3", "B4"}
    assert report.provider == "mock"
    assert report.real_llm_calls == 0
    assert report.baselines["B4"].ndcg_at_10 >= report.baselines["B0"].ndcg_at_10
    assert report.artifact_json()["mode"] == "ci_mini"


def test_ranking_artifact_omits_article_text_and_titles(mini_dataset):
    report = run_ranking_benchmark(mini_dataset, provider_name="mock")

    artifact = str(report.artifact_json())

    assert "AI agent benchmark" not in artifact
    assert "general update" not in artifact
    assert "top10_by_user" in artifact


def test_ranking_benchmark_fails_when_b4_ndcg_is_below_b0():
    now = datetime(2026, 6, 24, tzinfo=UTC)
    articles = []
    for index in range(12):
        article_id = index + 1
        articles.append(
            BenchmarkArticle(
                article_id=article_id,
                feed_ids=[1],
                title=f"Article {article_id}",
                tags=[],
                base_score=20 if article_id <= 10 else 95,
                published_at=now - timedelta(hours=index),
                risk_uncertainty=20,
                weak_label="must_read" if article_id <= 10 else "skip",
            )
        )
    dataset = BenchmarkDataset(
        users=[BenchmarkUser(user_id="user-1", priority_by_feed={1: 0})],
        articles=articles,
        generated_at=now,
    )

    report = run_ranking_benchmark(dataset, provider_name="mock")

    assert report.status == "failed"
    assert report.failure_reason == "b4_ndcg_below_b0"


def test_b4_baseline_uses_online_ranking_module(monkeypatch, mini_dataset):
    import app.benchmark.ranking as ranking

    class FakeRankingModule:
        class Candidate:
            def __init__(self, **values):
                self.__dict__.update(values)

        @staticmethod
        def rank_b4(**_kwargs):
            return [
                type("Ranked", (), {"article_id": 20})(),
                type("Ranked", (), {"article_id": 19})(),
            ]

    monkeypatch.setattr(ranking, "_load_online_ranking_module", lambda: FakeRankingModule)

    report = run_ranking_benchmark(mini_dataset, provider_name="mock")

    assert report.baselines["B4"].top10_by_user == {
        "user-1": [20, 19],
        "user-2": [20, 19],
    }


def test_run_benchmark_persists_ranking_metrics(mini_dataset):
    class RecordingSink:
        def __init__(self):
            self.dataset = mini_dataset
            self.saved = []

        def load_benchmark_dataset(self, benchmark_run_id):
            assert benchmark_run_id == 7
            return self.dataset

        def save_benchmark_result(self, benchmark_run_id, metrics, artifact_path, cost_estimate):
            self.saved.append((benchmark_run_id, metrics, artifact_path, cost_estimate))

    sink = RecordingSink()

    result = run_benchmark(
        {"benchmark_run_id": 7, "suite": "ranking", "mode": "ci_mini", "provider": "mock"},
        sink,
    )

    assert result["status"] == "succeeded"
    assert result["benchmark_run_id"] == 7
    assert sink.saved[0][0] == 7
    assert set(sink.saved[0][1]["baselines"]) >= {"B0", "B1", "B2", "B3", "B4"}
    assert sink.saved[0][3]["real_llm_calls"] == 0


def test_ci_mini_benchmark_rejects_non_mock_provider(mini_dataset):
    class RecordingSink:
        def load_benchmark_dataset(self, benchmark_run_id):
            return mini_dataset

        def save_benchmark_result(self, benchmark_run_id, metrics, artifact_path, cost_estimate):
            raise AssertionError("non-mock ci benchmark must not persist")

    with pytest.raises(BenchmarkRunRejected, match="mock"):
        run_benchmark(
            {
                "benchmark_run_id": 8,
                "suite": "ranking",
                "mode": "ci_mini",
                "provider": "minimax",
            },
            RecordingSink(),
        )


def test_manual_full_benchmark_requires_cost_within_limits(mini_dataset):
    class ExpensiveSink:
        def dry_run_benchmark_cost(self, benchmark_run_id):
            assert benchmark_run_id == 9
            return {"pair_count": 3_001, "estimated_cost_usd": 12.50}

    with pytest.raises(BenchmarkRunRejected, match="cost limits"):
        run_benchmark(
            {
                "benchmark_run_id": 9,
                "suite": "ranking",
                "mode": "manual_full",
                "max_pairs": 3_000,
                "max_cost_usd": 10.0,
            },
            ExpensiveSink(),
        )


def test_manual_full_benchmark_requires_dry_run_cost_estimate():
    class SinkWithoutDryRun:
        pass

    with pytest.raises(BenchmarkRunRejected, match="dry-run"):
        run_benchmark(
            {"benchmark_run_id": 10, "suite": "ranking", "mode": "manual_full"},
            SinkWithoutDryRun(),
        )

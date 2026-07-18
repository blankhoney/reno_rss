import json

from sqlalchemy import create_engine, text

from app.db.benchmark_sink import DatabaseBenchmarkSink


def test_database_benchmark_sink_loads_dataset_and_saves_result():
    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
    sink = DatabaseBenchmarkSink(engine=engine)

    dataset = sink.load_benchmark_dataset(7)
    cost = sink.dry_run_benchmark_cost(7)
    sink.save_benchmark_result(
        7,
        {"status": "succeeded", "baselines": {"B4": {"ndcg_at_10": 1.0}}},
        "benchmark_runs/7/ranking.json",
        {"provider": "mock", "real_llm_calls": 0},
    )

    with engine.begin() as connection:
        run = (
            connection.execute(text("SELECT * FROM benchmark_runs WHERE id = 7"))
            .mappings()
            .one()
        )

    assert [str(user.user_id) for user in dataset.users] == ["user-1", "user-2"]
    assert dataset.users[0].priority_by_feed == {1: 10}
    assert dataset.users[0].feedback_by_article == {
        1: {"feedback_type": "thumbs_up", "user_score": 90}
    }
    assert dataset.users[0].article_status_by_article == {2: "skipped"}
    assert [(article.article_id, article.feed_ids, article.weak_label) for article in dataset.articles] == [
        (1, [1], "must_read"),
        (2, [2], "read"),
    ]
    assert dataset.articles[0].tags == ["ai"]
    assert dataset.articles[0].risk_uncertainty == 12
    assert cost == {"pair_count": 4, "estimated_cost_usd": 0.0}
    assert run["status"] == "succeeded"
    assert run["artifact_path"] == "benchmark_runs/7/ranking.json"
    assert json.loads(run["metrics"])["baselines"]["B4"]["ndcg_at_10"] == 1.0
    assert json.loads(run["cost_estimate"])["provider"] == "mock"


def _create_schema(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE user_feed_subscriptions (
                user_id TEXT NOT NULL,
                feed_id INTEGER NOT NULL,
                enabled BOOLEAN NOT NULL,
                user_priority INTEGER NOT NULL
            );
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE user_article_feedback_scores (
                user_id TEXT NOT NULL,
                article_id INTEGER NOT NULL,
                feedback_type TEXT NOT NULL,
                user_score INTEGER NOT NULL
            );
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE user_article_states (
                user_id TEXT NOT NULL,
                article_id INTEGER NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                primary_feed_id INTEGER,
                title TEXT NOT NULL,
                published_at TEXT
            );
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE article_base_scores (
                article_id INTEGER NOT NULL,
                base_score INTEGER,
                recommendation_tier TEXT,
                tags TEXT,
                dimension_scores TEXT,
                risk_flags TEXT,
                is_active BOOLEAN NOT NULL,
                scoring_status TEXT NOT NULL
            );
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE article_sources (
                article_id INTEGER NOT NULL,
                feed_id INTEGER NOT NULL
            );
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE benchmark_runs (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                metrics TEXT NOT NULL,
                artifact_path TEXT,
                cost_estimate TEXT NOT NULL,
                completed_at TEXT
            );
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO app_users (id, created_at)
            VALUES ('user-1', '2026-07-08T00:00:00+00:00'),
                   ('user-2', '2026-07-08T00:01:00+00:00');
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO user_feed_subscriptions (user_id, feed_id, enabled, user_priority)
            VALUES ('user-1', 1, TRUE, 10),
                   ('user-2', 2, TRUE, 5),
                   ('user-1', 3, FALSE, 20);
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO user_article_feedback_scores (
                user_id, article_id, feedback_type, user_score
            )
            VALUES ('user-1', 1, 'thumbs_up', 90);
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO user_article_states (user_id, article_id, status)
            VALUES ('user-1', 2, 'skipped');
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO articles (id, primary_feed_id, title, published_at)
            VALUES (1, 1, 'AI agent benchmark', '2026-07-08T01:00:00+00:00'),
                   (2, 2, 'General update', '2026-07-08T00:30:00+00:00');
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO article_sources (article_id, feed_id)
            VALUES (1, 1),
                   (2, 2);
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO article_base_scores (
                article_id, base_score, recommendation_tier, tags,
                dimension_scores, risk_flags, is_active, scoring_status
            )
            VALUES (1, 91, 'must_read', '["ai"]', '{"risk_uncertainty": 12}',
                    '[]', TRUE, 'success'),
                   (2, 72, NULL, '["misc"]', '{}', '["low_context"]',
                    TRUE, 'success');
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO benchmark_runs (
                id, status, metrics, artifact_path, cost_estimate, completed_at
            )
            VALUES (7, 'queued', '{}', NULL, '{}', NULL);
            """
        )

from sqlalchemy import create_engine, text

from app.db.score_sink import DatabaseScoreSink


def test_score_sink_writes_success_and_error_rows_with_active_history():
    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
    sink = DatabaseScoreSink(engine=engine)

    articles = sink.list_batch_articles(10)
    first_score_id = sink.save_score(
        1,
        {
            "batch_id": 10,
            "base_score": 80,
            "recommendation_tier": "read",
            "dimension_scores": {"risk_uncertainty": 10},
            "dimension_reasons": {},
            "summary_zh": "摘要",
            "summary_original": "summary",
            "source_language": "en",
            "tags": ["ai"],
            "reason": "useful",
            "risk_flags": [],
            "confidence": 0.8,
            "scoring_status": "success",
            "model_provider": "mock",
            "model_name": "mock",
            "prompt_version": "v0",
        },
    )
    second_score_id = sink.save_score(
        1,
        {
            "batch_id": 10,
            "base_score": 90,
            "recommendation_tier": "must_read",
            "dimension_scores": {"risk_uncertainty": 5},
            "dimension_reasons": {},
            "summary_zh": "新摘要",
            "summary_original": "new summary",
            "source_language": "en",
            "tags": ["ai"],
            "reason": "better",
            "risk_flags": [],
            "confidence": 0.9,
            "scoring_status": "success",
            "model_provider": "mock",
            "model_name": "mock",
            "prompt_version": "v0",
        },
    )
    error_score_id = sink.save_score(
        2,
        {
            "batch_id": 10,
            "base_score": 5,
            "recommendation_tier": "skip",
            "dimension_scores": {},
            "dimension_reasons": {},
            "summary_zh": "",
            "summary_original": "",
            "source_language": "unknown",
            "tags": [],
            "reason": "评分失败，需重新评分。",
            "risk_flags": [],
            "confidence": 0.0,
            "scoring_status": "error",
            "error": "provider timeout",
            "model_provider": "baseline",
            "model_name": "length-baseline",
            "prompt_version": "rss-score-v04",
        },
    )

    with engine.begin() as connection:
        scores = (
            connection.execute(text("SELECT * FROM article_base_scores ORDER BY id"))
            .mappings()
            .all()
        )
        items = (
            connection.execute(text("SELECT * FROM scoring_batch_items ORDER BY article_id"))
            .mappings()
            .all()
        )

    assert [article["id"] for article in articles] == [1, 2]
    assert first_score_id != second_score_id
    assert error_score_id is not None
    assert [score["is_active"] for score in scores] == [0, 1, 0]
    assert [(item["article_id"], item["status"], item["base_score_id"]) for item in items] == [
        (1, "scored", second_score_id),
        (2, "error", error_score_id),
    ]


def _create_schema(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                content_text TEXT,
                content_html TEXT,
                content_hash TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE scoring_batches (
                id INTEGER PRIMARY KEY,
                status TEXT,
                finished_at TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE scoring_batch_items (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL,
                article_id INTEGER NOT NULL,
                status TEXT,
                base_score_id INTEGER,
                error TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE article_base_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                batch_id INTEGER,
                base_score INTEGER,
                recommendation_tier TEXT,
                summary_zh TEXT,
                summary_original TEXT,
                source_language TEXT,
                dimension_scores TEXT,
                dimension_reasons TEXT,
                tags TEXT,
                reason TEXT,
                risk_flags TEXT,
                confidence REAL,
                rubric_version TEXT,
                model_provider TEXT,
                model_name TEXT,
                prompt_version TEXT,
                input_content_hash TEXT,
                scoring_status TEXT,
                error TEXT,
                is_active INTEGER,
                scored_at TEXT
            )
            """
        )
        connection.execute(
            text(
                """
                INSERT INTO articles (id, title, url, content_text, content_hash)
                VALUES
                  (1, 'First', 'https://example.com/1', 'first text', 'hash-1'),
                  (2, 'Second', 'https://example.com/2', 'second text', 'hash-2')
                """
            )
        )
        connection.execute(text("INSERT INTO scoring_batches (id, status) VALUES (10, 'running')"))
        connection.execute(
            text(
                """
                INSERT INTO scoring_batch_items (id, batch_id, article_id, status)
                VALUES (1, 10, 1, 'pending'), (2, 10, 2, 'pending')
                """
            )
        )

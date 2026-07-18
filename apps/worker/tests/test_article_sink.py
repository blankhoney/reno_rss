from sqlalchemy import create_engine, text

from app.db.article_sink import DatabaseArticleSink


def test_article_sink_reuses_article_by_dedup_key_and_upserts_sources():
    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
    _seed_feeds(engine, 1, 2)
    sink = DatabaseArticleSink(engine=engine)

    first_article_id = sink.upsert_article(
        {
            "primary_feed_id": 1,
            "title": "First title",
            "url": "https://example.com/post?utm_source=newsletter",
            "canonical_url": "https://example.com/post",
            "published_at": "2026-06-24T09:00:00+08:00",
            "content_text": "hello world",
        }
    )
    sink.upsert_article_source(
        {
            "article_id": first_article_id,
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "source_url": "https://example.com/post?utm_source=newsletter",
            "source_title": "First title",
            "published_at": "2026-06-24T09:00:00+08:00",
        }
    )

    second_article_id = sink.upsert_article(
        {
            "primary_feed_id": 2,
            "title": "Second title",
            "url": "https://example.com/post?gclid=abc",
            "canonical_url": "https://example.com/post",
            "published_at": "2026-06-24T10:00:00+08:00",
        }
    )
    sink.upsert_article_source(
        {
            "article_id": second_article_id,
            "feed_id": 2,
            "miniflux_entry_id": 202,
            "source_url": "https://example.com/post?gclid=abc",
            "source_title": "Second title",
            "published_at": "2026-06-24T10:00:00+08:00",
        }
    )

    with engine.begin() as connection:
        articles = connection.execute(text("SELECT * FROM articles")).mappings().all()
        sources = (
            connection.execute(
                text("SELECT * FROM article_sources ORDER BY feed_id, miniflux_entry_id")
            )
            .mappings()
            .all()
        )

    assert second_article_id == first_article_id
    assert len(articles) == 1
    assert articles[0]["primary_feed_id"] == 1
    assert articles[0]["content_hash"]
    assert [(source["feed_id"], source["miniflux_entry_id"]) for source in sources] == [
        (1, 101),
        (2, 202),
    ]


def test_article_sink_source_upsert_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
    _seed_feeds(engine, 1)
    sink = DatabaseArticleSink(engine=engine)
    article_id = sink.upsert_article(
        {
            "primary_feed_id": 1,
            "title": "Title",
            "url": "https://example.com/post",
            "canonical_url": "https://example.com/post",
        }
    )

    source = {
        "article_id": article_id,
        "feed_id": 1,
        "miniflux_entry_id": 101,
        "source_url": "https://example.com/post",
        "source_title": "Old title",
        "published_at": None,
    }
    sink.upsert_article_source(source)
    sink.upsert_article_source({**source, "source_title": "New title"})

    with engine.begin() as connection:
        rows = connection.execute(text("SELECT * FROM article_sources")).mappings().all()

    assert len(rows) == 1
    assert rows[0]["source_title"] == "New title"


def test_article_sink_creates_feed_before_article_source_foreign_keys():
    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
    sink = DatabaseArticleSink(engine=engine)

    local_feed_id = sink.upsert_feed(
        {
            "feed_id": 31,
            "feed_url": "https://example.com/feed.xml",
            "feed_title": "Example Feed",
            "feed_site_url": "https://example.com",
        }
    )
    article_id = sink.upsert_article(
        {
            "primary_feed_id": local_feed_id,
            "title": "Entry title",
            "url": "https://example.com/post",
            "canonical_url": "https://example.com/post",
        }
    )
    sink.upsert_article_source(
        {
            "article_id": article_id,
            "feed_id": local_feed_id,
            "miniflux_entry_id": 101,
            "miniflux_category_id": 9,
            "source_url": "https://example.com/post",
            "source_title": "Entry title",
        }
    )

    with engine.begin() as connection:
        feed = connection.execute(text("SELECT * FROM feeds")).mappings().one()
        article = connection.execute(text("SELECT * FROM articles")).mappings().one()
        source = connection.execute(text("SELECT * FROM article_sources")).mappings().one()

    assert feed["id"] == local_feed_id
    assert feed["miniflux_feed_id"] == 31
    assert feed["feed_url"] == "https://example.com/feed.xml"
    assert feed["title"] == "Example Feed"
    assert article["primary_feed_id"] == local_feed_id
    assert source["feed_id"] == local_feed_id
    assert source["miniflux_category_id"] == 9


def test_article_sink_enqueues_partial_content_then_completion_barrier():
    import json

    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
    _seed_feeds(engine, 1)
    sink = DatabaseArticleSink(engine=engine)
    partial_id = sink.upsert_article(
        {
            "primary_feed_id": 1,
            "title": "Partial",
            "url": "https://example.com/partial",
            "canonical_url": "https://example.com/partial",
            "content_text": "short fragment",
            "content_quality": "partial",
        }
    )
    full_id = sink.upsert_article(
        {
            "primary_feed_id": 1,
            "title": "Full",
            "url": "https://example.com/full",
            "canonical_url": "https://example.com/full",
            "content_text": "full body",
            "content_quality": "full",
        }
    )

    result = sink.enqueue_ingest_followups(
        [partial_id, full_id],
        pipeline_cycle="2026-07-18T12:00:00+00:00",
        auto_score_payload={"lookback_hours": 72, "max_articles": 30},
    )

    with engine.begin() as connection:
        jobs = connection.execute(text("SELECT * FROM jobs ORDER BY id")).mappings().all()
    assert [job["job_type"] for job in jobs] == [
        "fetch_article_content",
        "complete_ingest_cycle",
    ]
    assert jobs[0]["priority"] == 4
    barrier_payload = json.loads(jobs[1]["payload"])
    assert barrier_payload["fetch_job_ids"] == [jobs[0]["id"]]
    assert result["content_fetches"] == 1


def test_ingest_barrier_enqueues_auto_score_after_fetch_completion():
    import json

    from app.jobs.complete_ingest import complete_ingest_cycle

    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
    _seed_feeds(engine, 1)
    sink = DatabaseArticleSink(engine=engine)
    article_id = sink.upsert_article(
        {
            "primary_feed_id": 1,
            "title": "Partial",
            "url": "https://example.com/pipeline",
            "canonical_url": "https://example.com/pipeline",
            "content_text": "fragment",
            "content_quality": "partial",
        }
    )
    followups = sink.enqueue_ingest_followups(
        [article_id],
        pipeline_cycle="2026-07-18T13:00:00+00:00",
        auto_score_payload={"lookback_hours": 72, "max_articles": 30},
    )
    with engine.begin() as connection:
        fetch = connection.execute(
            text("SELECT * FROM jobs WHERE job_type='fetch_article_content'")
        ).mappings().one()
        connection.execute(
            text("UPDATE jobs SET status='succeeded' WHERE id=:id"),
            {"id": fetch["id"]},
        )
        barrier = connection.execute(
            text("SELECT * FROM jobs WHERE id=:id"),
            {"id": followups["barrier_job_id"]},
        ).mappings().one()

    result = complete_ingest_cycle(json.loads(barrier["payload"]), sink)

    with engine.begin() as connection:
        auto_score = connection.execute(
            text("SELECT * FROM jobs WHERE job_type='auto_score_candidates'")
        ).mappings().one()
    assert result["auto_score_enqueued"] is True
    assert auto_score["priority"] == 3
    assert json.loads(auto_score["payload"])["pipeline_cycle"] == (
        "2026-07-18T13:00:00+00:00"
    )


def _create_schema(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql(
            """
            CREATE TABLE feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_url TEXT NOT NULL UNIQUE,
                canonical_url TEXT,
                miniflux_feed_id INTEGER UNIQUE,
                title TEXT,
                status TEXT DEFAULT 'active',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 0,
                payload TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                progress TEXT NOT NULL DEFAULT '{}',
                result TEXT NOT NULL DEFAULT '{}',
                locked_by TEXT,
                locked_at TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5,
                run_after TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                last_error TEXT,
                created_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                primary_feed_id INTEGER REFERENCES feeds(id),
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                canonical_url TEXT,
                author TEXT,
                published_at TEXT,
                content_text TEXT,
                content_html TEXT,
                content_source TEXT,
                content_quality TEXT,
                content_hash TEXT,
                dedup_key TEXT UNIQUE,
                fetched_at TEXT,
                content_expires_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE article_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                feed_id INTEGER NOT NULL REFERENCES feeds(id),
                miniflux_entry_id INTEGER NOT NULL,
                miniflux_category_id INTEGER,
                source_url TEXT,
                source_title TEXT,
                published_at TEXT,
                first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(feed_id, miniflux_entry_id),
                UNIQUE(article_id, feed_id, miniflux_entry_id)
            )
            """
        )


def _seed_feeds(engine, *feed_ids: int) -> None:
    with engine.begin() as connection:
        for feed_id in feed_ids:
            connection.execute(
                text(
                    """
                    INSERT INTO feeds (id, feed_url, title, status)
                    VALUES (:id, :feed_url, :title, 'active')
                    """
                ),
                {
                    "id": feed_id,
                    "feed_url": f"https://example.com/{feed_id}.xml",
                    "title": f"Feed {feed_id}",
                },
            )

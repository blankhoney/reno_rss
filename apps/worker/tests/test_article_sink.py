from sqlalchemy import create_engine, text

from app.db.article_sink import DatabaseArticleSink


def test_article_sink_reuses_article_by_dedup_key_and_upserts_sources():
    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
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


def _create_schema(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                primary_feed_id INTEGER,
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
                feed_id INTEGER NOT NULL,
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

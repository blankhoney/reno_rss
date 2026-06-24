from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text

from app.db.content_sink import DatabaseContentSink


def test_content_sink_loads_article_source_and_saves_content_fields():
    engine = create_engine("sqlite:///:memory:")
    _create_schema(engine)
    now = datetime(2026, 6, 24, 12, tzinfo=UTC)
    sink = DatabaseContentSink(engine=engine)

    article = sink.get_article_for_fetch(1)
    sink.save_content(
        1,
        {
            "content_html": "<article>Full text</article>",
            "content_text": "Full text",
            "content_source": "readability",
            "content_quality": "full",
            "fetched_at": now,
            "content_expires_at": now + timedelta(days=7),
        },
    )

    with engine.begin() as connection:
        row = connection.execute(text("SELECT * FROM articles WHERE id=1")).mappings().one()

    assert article is not None
    assert article["miniflux_entry_id"] == 101
    assert row["content_source"] == "readability"
    assert row["content_quality"] == "full"
    assert row["content_hash"]
    assert row["content_expires_at"] == "2026-07-01T12:00:00+00:00"


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
                content_source TEXT,
                content_quality TEXT,
                content_hash TEXT,
                fetched_at TEXT,
                content_expires_at TEXT,
                updated_at TEXT
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE article_sources (
                id INTEGER PRIMARY KEY,
                article_id INTEGER NOT NULL,
                feed_id INTEGER NOT NULL,
                miniflux_entry_id INTEGER NOT NULL,
                first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            text(
                """
                INSERT INTO articles (id, title, url, content_html, content_text)
                VALUES (1, 'Article', 'https://example.com/post', '<p>Short</p>', 'Short')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO article_sources (id, article_id, feed_id, miniflux_entry_id)
                VALUES (1, 1, 1, 101)
                """
            )
        )

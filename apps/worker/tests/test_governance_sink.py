from sqlalchemy import create_engine, text

from app.db.governance_sink import DatabaseGovernanceSink


def test_governance_demotes_through_existing_subscription_priority_schema():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE user_feed_subscriptions (
                user_id TEXT NOT NULL,
                feed_id INTEGER NOT NULL,
                enabled BOOLEAN NOT NULL,
                user_priority INTEGER
            )
            """
        )
        connection.execute(
            text(
                """
                INSERT INTO user_feed_subscriptions (user_id, feed_id, enabled, user_priority)
                VALUES
                    ('user-a', 7, TRUE, 5),
                    ('user-b', 7, TRUE, -25),
                    ('user-c', 8, TRUE, 0)
                """
            )
        )

    sink = DatabaseGovernanceSink(engine=engine)
    affected = sink.demote_feed(7, reason="quality")

    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT feed_id, user_priority
                FROM user_feed_subscriptions
                ORDER BY feed_id, user_id
                """
            )
        ).mappings().all()

    assert affected == 2
    assert [(row["feed_id"], row["user_priority"]) for row in rows] == [
        (7, -20),
        (7, -25),
        (8, 0),
    ]

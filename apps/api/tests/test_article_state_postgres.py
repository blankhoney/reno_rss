import os
from uuid import uuid4

import pytest


POSTGRES_URL = os.environ.get("ARTICLE_POSTGRES_TEST_URL")


@pytest.mark.skipif(POSTGRES_URL is None, reason="ARTICLE_POSTGRES_TEST_URL is not configured")
def test_postgres_article_state_preserves_independent_fields_and_rejects_invalid_project():
    from sqlalchemy import create_engine
    from sqlalchemy.exc import IntegrityError

    from app.db.auth_store import DatabaseAuthStore
    from app.db.models import articles, user_article_states
    from app.db.repositories.articles import DatabaseArticleRepository

    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    auth_store = DatabaseAuthStore(POSTGRES_URL, engine=engine)
    user, _, _ = auth_store.create_user(f"state-contract-{uuid4()}")
    with engine.begin() as connection:
        article_id = connection.execute(
            articles.insert()
            .values(
                title="Atomic state contract",
                url=f"https://example.test/state-contract/{uuid4()}",
                dedup_key=f"state-contract-{uuid4()}",
            )
            .returning(articles.c.id)
        ).scalar_one()

    repository = DatabaseArticleRepository(POSTGRES_URL, engine=engine)
    repository.upsert_state(user.id, article_id, saved=True)
    final_state = repository.upsert_state(user.id, article_id, status="read")
    assert final_state is not None
    assert final_state.status == "read"
    assert final_state.saved is True

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                user_article_states.insert().values(
                    user_id=user.id,
                    article_id=article_id,
                    saved=False,
                    project=True,
                )
            )

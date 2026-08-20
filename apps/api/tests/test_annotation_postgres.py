from collections import Counter
import os
from threading import Barrier, Thread
from uuid import uuid4

import pytest


POSTGRES_URL = os.environ.get("ARTICLE_POSTGRES_TEST_URL")


@pytest.mark.skipif(POSTGRES_URL is None, reason="ARTICLE_POSTGRES_TEST_URL is not configured")
def test_postgres_annotation_lifecycle_preserves_owner_and_tombstone():
    from sqlalchemy import create_engine, select

    from app.core.config import normalize_database_url
    from app.db.auth_store import DatabaseAuthStore
    from app.domain.annotations_meta import encode_annotation_content, searchable_annotation_body
    from app.db.models import article_annotations, articles
    from app.db.repositories.articles import AnnotationDeleteResult, DatabaseArticleRepository

    assert POSTGRES_URL is not None
    database_url = normalize_database_url(POSTGRES_URL)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        auth_store = DatabaseAuthStore(database_url, engine=engine)
        owner, _, _ = auth_store.create_user(f"annotation-owner-{uuid4()}")
        other, _, _ = auth_store.create_user(f"annotation-other-{uuid4()}")
        admin, _, _ = auth_store.create_user(f"annotation-admin-{uuid4()}", role="admin")
        with engine.begin() as connection:
            article_id = connection.execute(
                articles.insert()
                .values(
                    title="Annotation lifecycle",
                    url=f"https://example.test/annotation/{uuid4()}",
                    dedup_key=f"annotation-{uuid4()}",
                )
                .returning(articles.c.id)
            ).scalar_one()

        repository = DatabaseArticleRepository(database_url, engine=engine)
        anchor = {
            "kind": "text-quote",
            "version": 1,
            "exact": "old note",
            "prefix": "",
            "suffix": "",
            "start": 0,
            "end": 8,
        }
        created = repository.create_annotation(
            owner.id,
            article_id,
            content=encode_annotation_content("old note", anchor=anchor),
            selected_text=None,
            annotation_type="comment",
        )
        assert created is not None
        annotation_id = created.id

        updated = repository.update_annotation(
            owner.id,
            annotation_id,
            content=encode_annotation_content("new note", anchor=anchor),
        )
        assert updated is not None
        assert searchable_annotation_body(updated.content) == "new note"
        assert updated.selected_text is None
        assert updated.type == "comment"
        assert updated.deleted_at is None
        assert repository.search_annotations(owner.id, q="old note") == []
        assert [item.id for item in repository.search_annotations(owner.id, q="new note")] == [annotation_id]
        assert [item.id for item in repository.search_annotations(owner.id, q="NEW NOTE")] == [annotation_id]
        assert repository.search_annotations(other.id, q="new note") == []
        assert repository.update_annotation(other.id, annotation_id, content="intrusion") is None

        selected_anchor = {
            "kind": "text-quote",
            "version": 1,
            "exact": "selected old body",
            "prefix": "",
            "suffix": "",
            "start": 0,
            "end": 17,
        }
        selected = repository.create_annotation(
            owner.id,
            article_id,
            content=encode_annotation_content("selected old body", anchor=selected_anchor),
            selected_text="Kept Quote",
            annotation_type="annotation",
        )
        assert selected is not None
        selected_updated = repository.update_annotation(
            owner.id,
            selected.id,
            content=encode_annotation_content("selected new body", anchor=selected_anchor),
        )
        assert selected_updated is not None
        assert [item.id for item in repository.search_annotations(owner.id, q="KEPT QUOTE")] == [selected.id]

        assert (
            repository.soft_delete_annotation(other.id, annotation_id)
            is AnnotationDeleteResult.NOT_FOUND_OR_NOT_OWNER
        )
        assert (
            repository.soft_delete_annotation(admin.id, annotation_id)
            is AnnotationDeleteResult.NOT_FOUND_OR_NOT_OWNER
        )
        assert repository.get_annotation(owner.id, annotation_id) is not None
        assert (
            repository.soft_delete_annotation(owner.id, annotation_id)
            is AnnotationDeleteResult.DELETED
        )
        with engine.begin() as connection:
            first_tombstone = connection.execute(
                select(
                    article_annotations.c.deleted_at,
                    article_annotations.c.updated_at,
                    article_annotations.c.deleted_by,
                    article_annotations.c.delete_reason,
                ).where(article_annotations.c.id == annotation_id)
            ).one()
        assert (
            repository.soft_delete_annotation(owner.id, annotation_id)
            is AnnotationDeleteResult.ALREADY_DELETED
        )
        with engine.begin() as connection:
            repeated_tombstone = connection.execute(
                select(
                    article_annotations.c.deleted_at,
                    article_annotations.c.updated_at,
                    article_annotations.c.deleted_by,
                    article_annotations.c.delete_reason,
                ).where(article_annotations.c.id == annotation_id)
            ).one()
        assert repeated_tombstone == first_tombstone
        assert (
            repository.soft_delete_annotation(admin.id, annotation_id)
            is AnnotationDeleteResult.NOT_FOUND_OR_NOT_OWNER
        )
        assert (
            repository.soft_delete_annotation(owner.id, selected.id)
            is AnnotationDeleteResult.DELETED
        )
        assert (
            repository.soft_delete_annotation(owner.id, 2_147_483_647)
            is AnnotationDeleteResult.NOT_FOUND_OR_NOT_OWNER
        )
        assert repository.get_annotation(owner.id, annotation_id) is None
        assert repository.list_annotations(owner.id, article_id) == []
        assert repository.list_annotations_for_articles(owner.id, [article_id]) == {}
        assert repository.list_recent_annotations(owner.id) == []
        assert repository.list_due_annotations(owner.id) == []
        assert repository.search_annotations(owner.id, q="new note") == []

        assert first_tombstone.deleted_at is not None
        assert first_tombstone.deleted_at == first_tombstone.updated_at
        assert first_tombstone.deleted_by == owner.id
        assert first_tombstone.delete_reason == "user_request"
    finally:
        engine.dispose()


@pytest.mark.skipif(POSTGRES_URL is None, reason="ARTICLE_POSTGRES_TEST_URL is not configured")
def test_postgres_concurrent_annotation_delete_uses_read_committed():
    from sqlalchemy import create_engine, func, select, text

    from app.core.config import normalize_database_url
    from app.db.auth_store import DatabaseAuthStore
    from app.db.models import article_annotations, articles
    from app.db.repositories.articles import AnnotationDeleteResult, DatabaseArticleRepository

    assert POSTGRES_URL is not None
    database_url = normalize_database_url(POSTGRES_URL)
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        isolation_level="READ COMMITTED",
    )
    try:
        auth_store = DatabaseAuthStore(database_url, engine=engine)
        owner, _, _ = auth_store.create_user(f"annotation-race-owner-{uuid4()}")
        with engine.begin() as connection:
            article_id = connection.execute(
                articles.insert()
                .values(
                    title="Annotation delete race",
                    url=f"https://example.test/annotation-race/{uuid4()}",
                    dedup_key=f"annotation-race-{uuid4()}",
                )
                .returning(articles.c.id)
            ).scalar_one()
        barrier = Barrier(2)
        isolation_levels: list[str] = []

        def observe_delete_transaction(connection) -> None:
            isolation_levels.append(
                connection.execute(text("SHOW transaction_isolation")).scalar_one()
            )
            barrier.wait()

        repository = DatabaseArticleRepository(
            database_url,
            engine=engine,
            annotation_delete_transaction_observer=observe_delete_transaction,
        )
        annotation = repository.create_annotation(owner.id, article_id, content="race")
        assert annotation is not None

        results: list[AnnotationDeleteResult] = []
        errors: list[BaseException] = []

        def delete() -> None:
            try:
                results.append(repository.soft_delete_annotation(owner.id, annotation.id))
            except BaseException as error:
                errors.append(error)

        threads = [Thread(target=delete), Thread(target=delete)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert isolation_levels == ["read committed", "read committed"]
        assert Counter(results) == Counter(
            [AnnotationDeleteResult.DELETED, AnnotationDeleteResult.ALREADY_DELETED]
        )
        with engine.begin() as connection:
            rows = connection.execute(
                select(func.count()).select_from(article_annotations).where(
                    article_annotations.c.id == annotation.id
                )
            ).scalar_one()
            tombstone = connection.execute(
                select(article_annotations).where(article_annotations.c.id == annotation.id)
            ).mappings().one()
        assert rows == 1
        assert tombstone["deleted_at"] is not None
        assert repository.list_annotations(owner.id, article_id) == []
    finally:
        engine.dispose()


@pytest.mark.skipif(POSTGRES_URL is None, reason="ARTICLE_POSTGRES_TEST_URL is not configured")
def test_postgres_annotation_create_idempotency_replays_conflicts_and_scopes_owner():
    from sqlalchemy import create_engine

    from app.core.config import normalize_database_url
    from app.db.auth_store import DatabaseAuthStore
    from app.db.models import articles
    from app.db.repositories.articles import AnnotationCreateResultKind, DatabaseArticleRepository
    from app.domain.annotation_create import prepare_annotation_create

    assert POSTGRES_URL is not None
    database_url = normalize_database_url(POSTGRES_URL)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        auth_store = DatabaseAuthStore(database_url, engine=engine)
        owner, _, _ = auth_store.create_user(f"annotation-idem-owner-{uuid4()}")
        other, _, _ = auth_store.create_user(f"annotation-idem-other-{uuid4()}")
        with engine.begin() as connection:
            article_id = connection.execute(
                articles.insert().values(
                    title="Annotation idempotency",
                    url=f"https://example.test/annotation-idem/{uuid4()}",
                    dedup_key=f"annotation-idem-{uuid4()}",
                ).returning(articles.c.id)
            ).scalar_one()
        repository = DatabaseArticleRepository(database_url, engine=engine)
        prepared = prepare_annotation_create(
            content="same note", selected_text="quote", annotation_type="comment",
            color="yellow", tags=["ai"], anchor=None,
        )
        first = repository.create_annotation_idempotent(
            owner.id, article_id, idempotency_key="postgres-key-001",
            request_fingerprint=prepared.request_fingerprint, content=prepared.stored_content,
            selected_text=prepared.selected_text, annotation_type=prepared.annotation_type,
        )
        replay = repository.create_annotation_idempotent(
            owner.id, article_id, idempotency_key="postgres-key-001",
            request_fingerprint=prepared.request_fingerprint, content=prepared.stored_content,
            selected_text=prepared.selected_text, annotation_type=prepared.annotation_type,
        )
        conflict = repository.create_annotation_idempotent(
            owner.id, article_id, idempotency_key="postgres-key-001",
            request_fingerprint="0" * 64, content=prepared.stored_content,
            selected_text=prepared.selected_text, annotation_type=prepared.annotation_type,
        )
        other_result = repository.create_annotation_idempotent(
            other.id, article_id, idempotency_key="postgres-key-001",
            request_fingerprint=prepared.request_fingerprint, content=prepared.stored_content,
            selected_text=prepared.selected_text, annotation_type=prepared.annotation_type,
        )
        assert first.kind is AnnotationCreateResultKind.CREATED
        assert replay.kind is AnnotationCreateResultKind.REPLAYED
        assert replay.annotation is not None and first.annotation is not None
        assert replay.annotation.id == first.annotation.id
        assert conflict.kind is AnnotationCreateResultKind.CONFLICT
        assert other_result.kind is AnnotationCreateResultKind.CREATED
    finally:
        engine.dispose()

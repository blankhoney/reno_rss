from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, select, update

from app.core.config import normalize_database_url
from app.db.models import articles
from app.db.repositories.articles import MemoryArticleRepository
from app.db.repositories.jobs import (
    JobRecord,
    MemoryJobRepository,
    dedupe_key_for,
    enqueue_job_in_transaction,
)


TRANSLATION_JOB_TYPE = "translate_article"


@dataclass(frozen=True)
class TranslationEnqueueResult:
    kind: Literal["missing", "cached", "enqueued"]
    status: str | None = None
    content_zh: str | None = None
    translated_at: datetime | None = None
    job: JobRecord | None = None


class TranslationEnqueueStore(Protocol):
    def enqueue(self, article_id: int, *, created_by: UUID) -> TranslationEnqueueResult: ...


class MemoryTranslationEnqueueStore:
    def __init__(
        self,
        article_repository: MemoryArticleRepository,
        job_repository: MemoryJobRepository,
        lock: RLock,
        *,
        before_article_update: Callable[[], None] | None = None,
    ) -> None:
        if article_repository._lock is not lock or job_repository._lock is not lock:
            raise ValueError("memory translation repositories must share the supplied lock")
        self.article_repository = article_repository
        self.job_repository = job_repository
        self._lock = lock
        self._before_article_update = before_article_update

    def enqueue(self, article_id: int, *, created_by: UUID) -> TranslationEnqueueResult:
        with self._lock:
            article = self.article_repository.get_article(article_id)
            if article is None:
                return TranslationEnqueueResult(kind="missing")
            if article.content_zh and article.content_zh_status == "succeeded":
                return TranslationEnqueueResult(
                    kind="cached",
                    status="succeeded",
                    content_zh=article.content_zh,
                    translated_at=article.translated_at,
                )

            article_snapshot = self.article_repository._snapshot_translation_locked(article_id)
            job_snapshot = self.job_repository._snapshot_locked()
            try:
                job = self.job_repository.enqueue(
                    TRANSLATION_JOB_TYPE,
                    {"article_id": article_id},
                    dedupe_key=dedupe_key_for(TRANSLATION_JOB_TYPE, article_id),
                    created_by=created_by,
                )
                if job.status not in {"queued", "running"}:
                    raise RuntimeError("failed to enqueue or find active deduped job")
                if self._before_article_update is not None:
                    self._before_article_update()
                updated = self.article_repository.save_translation(
                    article_id,
                    content_zh=article.content_zh,
                    status=job.status,
                    translated_at=article.translated_at,
                )
                if updated is None:
                    raise RuntimeError("article disappeared during translation enqueue")
            except Exception:
                self.article_repository._restore_translation_locked(article_id, article_snapshot)
                self.job_repository._restore_locked(job_snapshot)
                raise

            return TranslationEnqueueResult(
                kind="enqueued",
                status=job.status,
                job=job,
            )


class DatabaseTranslationEnqueueStore:
    def __init__(
        self,
        database_url: str,
        engine: Engine | None = None,
        *,
        after_article_lock: Callable[[], None] | None = None,
        before_article_update: Callable[[], None] | None = None,
    ) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)
        self._after_article_lock = after_article_lock
        self._before_article_update = before_article_update

    def enqueue(self, article_id: int, *, created_by: UUID) -> TranslationEnqueueResult:
        with self.engine.begin() as connection:
            return self.enqueue_in_transaction(
                connection,
                article_id=article_id,
                created_by=created_by,
            )

    def enqueue_in_transaction(
        self,
        connection,
        *,
        article_id: int,
        created_by: UUID,
    ) -> TranslationEnqueueResult:
        article_row = (
            connection.execute(
                select(articles).where(articles.c.id == article_id).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if article_row is None:
            return TranslationEnqueueResult(kind="missing")
        if self._after_article_lock is not None:
            self._after_article_lock()
        if article_row["content_zh"] and article_row["content_zh_status"] == "succeeded":
            return TranslationEnqueueResult(
                kind="cached",
                status="succeeded",
                content_zh=article_row["content_zh"],
                translated_at=article_row["translated_at"],
            )

        job = enqueue_job_in_transaction(
            connection,
            dialect_name=self.engine.dialect.name,
            job_type=TRANSLATION_JOB_TYPE,
            payload={"article_id": article_id},
            dedupe_key=dedupe_key_for(TRANSLATION_JOB_TYPE, article_id),
            created_by=created_by,
            lock_reused_active=True,
        )
        if self._before_article_update is not None:
            self._before_article_update()
        updated_id = connection.execute(
            update(articles)
            .where(articles.c.id == article_id)
            .values(
                content_zh_status=job.status,
                updated_at=datetime.now(UTC),
            )
            .returning(articles.c.id)
        ).scalar_one_or_none()
        if updated_id is None:
            raise RuntimeError("article disappeared during translation enqueue")
        return TranslationEnqueueResult(
            kind="enqueued",
            status=job.status,
            job=job,
        )

    def dispose(self) -> None:
        self.engine.dispose()


def create_translation_enqueue_store(
    database_url: str | None,
    *,
    article_repository: MemoryArticleRepository | None = None,
    job_repository: MemoryJobRepository | None = None,
    lock: RLock | None = None,
) -> TranslationEnqueueStore:
    if database_url:
        normalized = normalize_database_url(database_url) or database_url
        return DatabaseTranslationEnqueueStore(normalized)
    if article_repository is None or job_repository is None or lock is None:
        raise ValueError("memory translation enqueue requires shared repositories and lock")
    return MemoryTranslationEnqueueStore(article_repository, job_repository, lock)

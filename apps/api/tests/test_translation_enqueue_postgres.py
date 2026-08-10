import os
from dataclasses import dataclass, field
from threading import Barrier, Event, Lock, Thread
from time import monotonic
from uuid import UUID, uuid4

import pytest


POSTGRES_URL = os.environ.get("ARTICLE_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(
    POSTGRES_URL is None,
    reason="ARTICLE_POSTGRES_TEST_URL is not configured",
)


def _engine_and_url():
    from sqlalchemy import create_engine

    from app.core.config import normalize_database_url

    assert POSTGRES_URL is not None
    database_url = normalize_database_url(POSTGRES_URL)
    return create_engine(database_url, pool_pre_ping=True), database_url


@dataclass
class PostgresCase:
    engine: object
    database_url: str
    user_ids: set[UUID] = field(default_factory=set)
    article_ids: set[int] = field(default_factory=set)


@pytest.fixture
def postgres_case():
    from sqlalchemy import delete, select, text

    from app.db.models import app_users, articles, job_watchers, jobs

    engine, database_url = _engine_and_url()
    case = PostgresCase(engine=engine, database_url=database_url)
    guard_connection = engine.connect()
    guard_transaction = guard_connection.begin()
    try:
        guard_connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        guard_connection.execute(text("SET LOCAL statement_timeout = '6s'"))
        # Serialize this module and lock pre-existing eligible rows. Global claim
        # calls can then only observe this case's newly inserted queued jobs.
        guard_connection.execute(text("SELECT pg_advisory_xact_lock(731947205)"))
        guard_connection.execute(
            select(jobs.c.id)
            .where(jobs.c.status == "queued", jobs.c.run_after <= text("NOW()"))
            .with_for_update()
        ).all()
        yield case
    finally:
        try:
            # Pytest reports teardown errors separately from call failures, so a
            # cleanup failure is visible without replacing the original assertion.
            with engine.begin() as connection:
                owned_job_ids = select(jobs.c.id).where(
                    jobs.c.payload["article_id"].astext.in_(
                        [str(article_id) for article_id in case.article_ids]
                    )
                )
                connection.execute(
                    delete(job_watchers).where(job_watchers.c.job_id.in_(owned_job_ids))
                )
                connection.execute(delete(jobs).where(jobs.c.id.in_(owned_job_ids)))
                connection.execute(delete(articles).where(articles.c.id.in_(case.article_ids)))
                connection.execute(delete(app_users).where(app_users.c.id.in_(case.user_ids)))
        finally:
            if guard_transaction.is_active:
                guard_transaction.rollback()
            guard_connection.close()
            engine.dispose()


def _seed_users_and_article(case: PostgresCase, *, label: str):
    from app.db.auth_store import DatabaseAuthStore
    from app.db.models import articles

    auth_store = DatabaseAuthStore(case.database_url, engine=case.engine)
    first, _, _ = auth_store.create_user(f"translation-{label}-first-{uuid4()}")
    case.user_ids.add(first.id)
    second, _, _ = auth_store.create_user(f"translation-{label}-second-{uuid4()}")
    case.user_ids.add(second.id)
    with case.engine.begin() as connection:
        article_id = connection.execute(
            articles.insert()
            .values(
                title=f"Translation {label}",
                url=f"https://example.test/translation/{label}/{uuid4()}",
                dedup_key=f"translation-{label}-{uuid4()}",
            )
            .returning(articles.c.id)
        ).scalar_one()
    case.article_ids.add(article_id)
    return first, second, article_id


def _prioritize_job(engine, job_id: int) -> None:
    from sqlalchemy import update

    from app.db.models import jobs

    with engine.begin() as connection:
        connection.execute(update(jobs).where(jobs.c.id == job_id).values(priority=1_000_000_000))


def _load_state(engine, article_id: int, job_id: int):
    from sqlalchemy import select

    from app.db.models import articles, job_watchers, jobs

    with engine.begin() as connection:
        article_status = connection.execute(
            select(articles.c.content_zh_status).where(articles.c.id == article_id)
        ).scalar_one()
        job_status = connection.execute(
            select(jobs.c.status).where(jobs.c.id == job_id)
        ).scalar_one()
        watchers = set(
            connection.execute(
                select(job_watchers.c.user_id).where(job_watchers.c.job_id == job_id)
            ).scalars()
        )
    return article_status, job_status, watchers


def _wait_until_blocked(control_connection, *, waiting_pid: int, blocking_pid: int) -> None:
    from sqlalchemy import text

    deadline = monotonic() + 3
    while monotonic() < deadline:
        row = control_connection.execute(
            text(
                """
                SELECT wait_event_type, pg_blocking_pids(pid) AS blockers
                FROM pg_stat_activity
                WHERE pid=:pid
                """
            ),
            {"pid": waiting_pid},
        ).mappings().one()
        if row["wait_event_type"] == "Lock" and blocking_pid in row["blockers"]:
            return
    raise AssertionError(
        f"backend {waiting_pid} was not observed waiting for backend {blocking_pid}"
    )


def test_postgres_translation_atomic_matrix(monkeypatch, postgres_case):
    from sqlalchemy import func, select, update
    from sqlalchemy.exc import IntegrityError

    from app.db.models import articles, job_watchers, jobs
    from app.db.repositories import jobs as jobs_module
    from app.db.repositories.jobs import claim_next_job_in_transaction
    from app.db.repositories.translation_enqueue import DatabaseTranslationEnqueueStore

    engine = postgres_case.engine
    database_url = postgres_case.database_url
    store = DatabaseTranslationEnqueueStore(database_url, engine=engine)
    try:
        first, second, article_id = _seed_users_and_article(
            postgres_case,
            label="matrix",
        )
        fresh = store.enqueue(article_id, created_by=first.id)
        assert fresh.kind == "enqueued"
        assert fresh.job is not None
        assert fresh.status == "queued"
        deduped = store.enqueue(article_id, created_by=second.id)
        assert deduped.job is not None
        assert deduped.job.id == fresh.job.id
        assert _load_state(engine, article_id, fresh.job.id) == (
            "queued",
            "queued",
            {first.id, second.id},
        )
        _prioritize_job(engine, fresh.job.id)

        with engine.begin() as connection:
            claimed = claim_next_job_in_transaction(connection, "matrix-worker")
        assert claimed is not None
        assert claimed.id == fresh.job.id
        running = store.enqueue(article_id, created_by=second.id)
        assert running.job is not None
        assert running.job.id == fresh.job.id
        assert running.status == "running"
        assert _load_state(engine, article_id, fresh.job.id)[0:2] == ("running", "running")

        assert store.enqueue(999_999_999, created_by=first.id).kind == "missing"

        _cached_first, _cached_second, cached_article_id = _seed_users_and_article(
            postgres_case,
            label="cached",
        )
        with engine.begin() as connection:
            connection.execute(
                update(articles)
                .where(articles.c.id == cached_article_id)
                .values(content_zh="cached", content_zh_status="succeeded")
            )
        cached = store.enqueue(cached_article_id, created_by=first.id)
        assert cached.kind == "cached"
        assert cached.content_zh == "cached"

        _failure_first, _failure_second, failure_article_id = _seed_users_and_article(
            postgres_case,
            label="watcher-failure",
        )
        original_watch = jobs_module._watch_job

        def fail_after_watcher(*args, **kwargs):
            original_watch(*args, **kwargs)
            raise RuntimeError("watcher failure")

        monkeypatch.setattr(jobs_module, "_watch_job", fail_after_watcher)
        with pytest.raises(RuntimeError, match="watcher failure"):
            store.enqueue(failure_article_id, created_by=first.id)
        monkeypatch.setattr(jobs_module, "_watch_job", original_watch)
        with engine.begin() as connection:
            assert connection.execute(
                select(articles.c.content_zh_status).where(articles.c.id == failure_article_id)
            ).scalar_one() is None
            leaked_jobs = connection.execute(
                select(func.count()).select_from(jobs).where(
                    jobs.c.payload["article_id"].astext == str(failure_article_id)
                )
            ).scalar_one()
            leaked_watchers = connection.execute(
                select(func.count())
                .select_from(job_watchers)
                .join(jobs, jobs.c.id == job_watchers.c.job_id)
                .where(jobs.c.payload["article_id"].astext == str(failure_article_id))
            ).scalar_one()
        assert leaked_jobs == 0
        assert leaked_watchers == 0

        _fk_first, _fk_second, fk_article_id = _seed_users_and_article(
            postgres_case,
            label="job-fk-failure",
        )
        with pytest.raises(IntegrityError):
            store.enqueue(fk_article_id, created_by=uuid4())
        with engine.begin() as connection:
            assert connection.execute(
                select(articles.c.content_zh_status).where(articles.c.id == fk_article_id)
            ).scalar_one() is None
            assert connection.execute(
                select(func.count()).select_from(jobs).where(
                    jobs.c.payload["article_id"].astext == str(fk_article_id)
                )
            ).scalar_one() == 0

        _article_fail_first, _article_fail_second, article_fail_id = _seed_users_and_article(
            postgres_case,
            label="article-failure",
        )

        def fail_article_update() -> None:
            raise RuntimeError("article update failure")

        failing_store = DatabaseTranslationEnqueueStore(
            database_url,
            engine=engine,
            before_article_update=fail_article_update,
        )
        with pytest.raises(RuntimeError, match="article update failure"):
            failing_store.enqueue(article_fail_id, created_by=first.id)
        with engine.begin() as connection:
            assert connection.execute(
                select(articles.c.content_zh_status).where(articles.c.id == article_fail_id)
            ).scalar_one() is None
            assert connection.execute(
                select(func.count()).select_from(jobs).where(
                    jobs.c.payload["article_id"].astext == str(article_fail_id)
                )
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_postgres_translation_lock_blocks_claim_until_commit(postgres_case):
    from app.db.repositories.jobs import DatabaseJobRepository
    from app.db.repositories.translation_enqueue import DatabaseTranslationEnqueueStore

    engine = postgres_case.engine
    database_url = postgres_case.database_url
    first, second, article_id = _seed_users_and_article(postgres_case, label="claim-after")
    initial_store = DatabaseTranslationEnqueueStore(database_url, engine=engine)
    initial = initial_store.enqueue(article_id, created_by=first.id)
    assert initial.job is not None
    _prioritize_job(engine, initial.job.id)

    locked = Event()
    release = Event()
    completed = Event()
    outcome: dict[str, object] = {}

    def before_article_update() -> None:
        locked.set()
        assert release.wait(timeout=3)

    translation_engine, _ = _engine_and_url()
    translation_store = DatabaseTranslationEnqueueStore(
        database_url,
        engine=translation_engine,
        before_article_update=before_article_update,
    )

    def translate() -> None:
        try:
            outcome["result"] = translation_store.enqueue(article_id, created_by=second.id)
        finally:
            completed.set()

    thread = Thread(target=translate)
    thread.start()
    try:
        assert locked.wait(timeout=3)
        claim_engine, _ = _engine_and_url()
        try:
            claim_repository = DatabaseJobRepository(database_url, engine=claim_engine)
            outcome["claim"] = claim_repository.claim_next("claim-during-translation")
        finally:
            claim_engine.dispose()
        assert outcome["claim"] is None
        release.set()
        assert completed.wait(timeout=3)
        thread.join(timeout=3)
        assert not thread.is_alive()
        result = outcome["result"]
        assert result.status == "queued"
        assert _load_state(engine, article_id, initial.job.id) == (
            "queued",
            "queued",
            {first.id, second.id},
        )
    finally:
        release.set()
        thread.join(timeout=3)
        translation_engine.dispose()
        engine.dispose()


def test_postgres_translation_lock_prevents_concurrent_cancel_commit(postgres_case):
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from app.db.repositories.jobs import cancel_job_in_transaction
    from app.db.repositories.translation_enqueue import DatabaseTranslationEnqueueStore

    engine = postgres_case.engine
    database_url = postgres_case.database_url
    first, second, article_id = _seed_users_and_article(postgres_case, label="cancel-after")
    initial = DatabaseTranslationEnqueueStore(database_url, engine=engine).enqueue(
        article_id,
        created_by=first.id,
    )
    assert initial.job is not None
    locked = Event()
    release = Event()
    translation_done = Event()
    cancel_done = Event()
    outcome: dict[str, object] = {}

    def before_article_update() -> None:
        locked.set()
        assert release.wait(timeout=3)

    translation_engine, _ = _engine_and_url()
    translation_store = DatabaseTranslationEnqueueStore(
        database_url,
        engine=translation_engine,
        before_article_update=before_article_update,
    )

    def translate() -> None:
        try:
            outcome["result"] = translation_store.enqueue(article_id, created_by=second.id)
        finally:
            translation_done.set()

    def cancel() -> None:
        cancel_engine, _ = _engine_and_url()
        try:
            with cancel_engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '200ms'"))
                cancel_job_in_transaction(connection, initial.job.id)
        except OperationalError as error:
            outcome["cancel_error"] = error
        finally:
            cancel_engine.dispose()
            cancel_done.set()

    translation_thread = Thread(target=translate)
    cancel_thread = Thread(target=cancel)
    cancel_started = False
    translation_thread.start()
    try:
        assert locked.wait(timeout=3)
        cancel_thread.start()
        cancel_started = True
        assert cancel_done.wait(timeout=3)
        assert "cancel_error" in outcome
        release.set()
        assert translation_done.wait(timeout=3)
        translation_thread.join(timeout=3)
        cancel_thread.join(timeout=3)
        result = outcome["result"]
        assert result.status == "queued"
        assert _load_state(engine, article_id, initial.job.id) == (
            "queued",
            "queued",
            {first.id, second.id},
        )
    finally:
        release.set()
        translation_thread.join(timeout=3)
        if cancel_started:
            cancel_thread.join(timeout=3)
        translation_engine.dispose()
        engine.dispose()


def test_postgres_translation_concurrent_enqueue_dedupes_and_watches(postgres_case):
    from sqlalchemy import func, select

    from app.db.models import articles, job_watchers, jobs
    from app.db.repositories.translation_enqueue import DatabaseTranslationEnqueueStore

    engine = postgres_case.engine
    database_url = postgres_case.database_url
    first, second, article_id = _seed_users_and_article(
        postgres_case,
        label="concurrent-enqueue",
    )
    start = Barrier(3)
    first_article_lock = Event()
    release_first = Event()
    winner_lock = Lock()
    winner_chosen = False
    outcomes: dict[UUID, object] = {}
    errors: dict[UUID, BaseException] = {}
    worker_engines = [_engine_and_url()[0], _engine_and_url()[0]]

    def hold_first_article_lock() -> None:
        nonlocal winner_chosen
        with winner_lock:
            is_first = not winner_chosen
            winner_chosen = True
        if is_first:
            first_article_lock.set()
            assert release_first.wait(timeout=3)

    def enqueue(user_id: UUID, worker_engine) -> None:
        from sqlalchemy import text

        store = DatabaseTranslationEnqueueStore(
            database_url,
            engine=worker_engine,
            after_article_lock=hold_first_article_lock,
        )
        connection = worker_engine.connect()
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL lock_timeout = '4s'"))
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            start.wait(timeout=3)
            outcomes[user_id] = store.enqueue_in_transaction(
                connection,
                article_id=article_id,
                created_by=user_id,
            )
            transaction.commit()
        except BaseException as error:
            errors[user_id] = error
            if transaction.is_active:
                transaction.rollback()
        finally:
            connection.close()

    threads = [
        Thread(target=enqueue, args=(first.id, worker_engines[0])),
        Thread(target=enqueue, args=(second.id, worker_engines[1])),
    ]
    for thread in threads:
        thread.start()
    try:
        start.wait(timeout=3)
        assert first_article_lock.wait(timeout=3)
        assert outcomes == {}
        assert errors == {}
        release_first.set()
        for thread in threads:
            thread.join(timeout=5)
            assert not thread.is_alive()
        assert errors == {}

        results = [outcomes[first.id], outcomes[second.id]]
        assert all(result.kind == "enqueued" for result in results)
        assert all(result.status == "queued" for result in results)
        assert all(result.job is not None for result in results)
        job_ids = {result.job.id for result in results}
        assert len(job_ids) == 1
        job_id = job_ids.pop()
        with engine.begin() as connection:
            active_jobs = connection.execute(
                select(func.count()).select_from(jobs).where(
                    jobs.c.job_type == "translate_article",
                    jobs.c.payload["article_id"].astext == str(article_id),
                    jobs.c.status.in_(("queued", "running")),
                )
            ).scalar_one()
            watchers = set(
                connection.execute(
                    select(job_watchers.c.user_id).where(job_watchers.c.job_id == job_id)
                ).scalars()
            )
            article_status = connection.execute(
                select(articles.c.content_zh_status).where(articles.c.id == article_id)
            ).scalar_one()
            job_status = connection.execute(
                select(jobs.c.status).where(jobs.c.id == job_id)
            ).scalar_one()
        assert active_jobs == 1
        assert watchers == {first.id, second.id}
        assert (article_status, job_status) == ("queued", "queued")
    finally:
        release_first.set()
        start.abort()
        for thread in threads:
            thread.join(timeout=6)
        for worker_engine in worker_engines:
            worker_engine.dispose()
        engine.dispose()


@pytest.mark.parametrize("transition", ["claim", "cancel"])
def test_postgres_translation_waits_for_job_holder_and_revalidates(
    transition, postgres_case
):
    from sqlalchemy import text

    from app.db.repositories.jobs import (
        cancel_job_in_transaction,
        claim_next_job_in_transaction,
    )
    from app.db.repositories.translation_enqueue import DatabaseTranslationEnqueueStore

    engine = postgres_case.engine
    database_url = postgres_case.database_url
    first, second, article_id = _seed_users_and_article(
        postgres_case,
        label=f"holder-{transition}",
    )
    initial = DatabaseTranslationEnqueueStore(database_url, engine=engine).enqueue(
        article_id,
        created_by=first.id,
    )
    assert initial.job is not None
    _prioritize_job(engine, initial.job.id)

    holder_engine, _ = _engine_and_url()
    waiter_engine, _ = _engine_and_url()
    control_engine, _ = _engine_and_url()
    holder_connection = holder_engine.connect()
    holder_transaction = holder_connection.begin()
    control_connection = control_engine.connect()
    holder_pid = holder_connection.execute(text("SELECT pg_backend_pid()" )).scalar_one()
    holder_connection.execute(text("SET LOCAL statement_timeout = '5s'"))
    if transition == "claim":
        held = claim_next_job_in_transaction(holder_connection, f"holder-{uuid4()}")
    else:
        held = cancel_job_in_transaction(holder_connection, initial.job.id)
    assert held is not None
    assert held.id == initial.job.id

    article_locked = Event()
    waiter_done = Event()
    outcome: dict[str, object] = {}

    def after_article_lock() -> None:
        article_locked.set()

    waiter_store = DatabaseTranslationEnqueueStore(
        database_url,
        engine=waiter_engine,
        after_article_lock=after_article_lock,
    )

    def wait_and_enqueue() -> None:
        connection = waiter_engine.connect()
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL lock_timeout = '4s'"))
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            outcome["waiter_pid"] = connection.execute(
                text("SELECT pg_backend_pid()")
            ).scalar_one()
            outcome["result"] = waiter_store.enqueue_in_transaction(
                connection,
                article_id=article_id,
                created_by=second.id,
            )
            transaction.commit()
        except Exception as error:
            outcome["error"] = error
            transaction.rollback()
        finally:
            connection.close()
            waiter_done.set()

    waiter_thread = Thread(target=wait_and_enqueue)
    waiter_thread.start()
    try:
        assert article_locked.wait(timeout=3)
        waiting_pid = int(outcome["waiter_pid"])
        _wait_until_blocked(
            control_connection,
            waiting_pid=waiting_pid,
            blocking_pid=holder_pid,
        )
        assert not waiter_done.is_set()
        holder_transaction.commit()
        assert waiter_done.wait(timeout=5)
        waiter_thread.join(timeout=3)
        assert not waiter_thread.is_alive()
        assert "error" not in outcome
        result = outcome["result"]
        if transition == "claim":
            assert result.job.id == initial.job.id
            assert result.status == "running"
            assert _load_state(engine, article_id, initial.job.id) == (
                "running",
                "running",
                {first.id, second.id},
            )
        else:
            assert result.job.id != initial.job.id
            assert result.status == "queued"
            article_status, new_job_status, watchers = _load_state(
                engine,
                article_id,
                result.job.id,
            )
            assert (article_status, new_job_status, watchers) == (
                "queued",
                "queued",
                {second.id},
            )
            assert _load_state(engine, article_id, initial.job.id)[1] == "cancelled"
    finally:
        if holder_transaction.is_active:
            holder_transaction.rollback()
        waiter_thread.join(timeout=3)
        holder_connection.close()
        control_connection.close()
        holder_engine.dispose()
        waiter_engine.dispose()
        control_engine.dispose()
        engine.dispose()

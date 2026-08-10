from threading import Event, RLock, Thread
from uuid import UUID, uuid4

import pytest

from app.db.repositories.articles import MemoryArticleRepository
from app.db.repositories.jobs import MemoryJobRepository
from app.db.repositories.translation_enqueue import MemoryTranslationEnqueueStore


def _repositories():
    lock = RLock()
    articles = MemoryArticleRepository(lock=lock)
    jobs = MemoryJobRepository(lock=lock)
    store = MemoryTranslationEnqueueStore(articles, jobs, lock)
    article = articles.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 901,
            "url": "https://example.com/atomic-translation",
            "title": "Atomic translation",
        }
    )
    return lock, articles, jobs, store, article


def test_memory_translation_fresh_enqueue_is_visible_to_creator():
    _lock, articles, jobs, store, article = _repositories()
    user_id = uuid4()

    result = store.enqueue(article.id, created_by=user_id)

    assert result.kind == "enqueued"
    assert result.status == "queued"
    assert result.job is not None
    assert articles.get_article(article.id).content_zh_status == "queued"
    assert jobs.get_visible_job(result.job.id, current_user_id=user_id, is_admin=False) == result.job


def test_memory_translation_cached_and_missing_do_not_enqueue():
    _lock, articles, jobs, store, article = _repositories()
    user_id = uuid4()
    articles.save_translation(
        article.id,
        content_zh="cached",
        status="succeeded",
        translated_at=None,
    )

    cached = store.enqueue(article.id, created_by=user_id)
    missing = store.enqueue(999999, created_by=user_id)

    assert cached.kind == "cached"
    assert cached.content_zh == "cached"
    assert missing.kind == "missing"
    assert jobs._jobs == {}
    assert jobs._watchers_by_job == {}


def test_memory_translation_rolls_back_new_job_watcher_and_next_id(monkeypatch):
    _lock, articles, jobs, store, article = _repositories()
    user_id = uuid4()
    original_watch = jobs._watch_job

    def fail_after_watch(job_id: int, watcher_id: UUID | None) -> None:
        original_watch(job_id, watcher_id)
        raise RuntimeError("watcher insert failed")

    monkeypatch.setattr(jobs, "_watch_job", fail_after_watch)

    with pytest.raises(RuntimeError, match="watcher insert failed"):
        store.enqueue(article.id, created_by=user_id)

    assert articles.get_article(article.id).content_zh_status is None
    assert jobs._jobs == {}
    assert jobs._watchers_by_job == {}
    assert jobs._next_id == 1


def test_memory_translation_rolls_back_second_watcher_with_defensive_copy():
    lock, articles, jobs, store, article = _repositories()
    first_user = uuid4()
    second_user = uuid4()
    first = store.enqueue(article.id, created_by=first_user)
    assert first.job is not None

    def fail_article_update() -> None:
        raise RuntimeError("article update failed")

    failing_store = MemoryTranslationEnqueueStore(
        articles,
        jobs,
        lock,
        before_article_update=fail_article_update,
    )

    with pytest.raises(RuntimeError, match="article update failed"):
        failing_store.enqueue(article.id, created_by=second_user)

    assert jobs._watchers_by_job[first.job.id] == {first_user}
    assert jobs.get_visible_job(first.job.id, current_user_id=second_user, is_admin=False) is None
    assert articles.get_article(article.id).content_zh_status == "queued"


def test_memory_translation_rolls_back_when_article_save_raises(monkeypatch):
    _lock, articles, jobs, store, article = _repositories()
    user_id = uuid4()

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("article write failed")

    monkeypatch.setattr(articles, "save_translation", fail_save)

    with pytest.raises(RuntimeError, match="article write failed"):
        store.enqueue(article.id, created_by=user_id)

    assert articles.get_article(article.id).content_zh_status is None
    assert jobs._jobs == {}
    assert jobs._watchers_by_job == {}
    assert jobs._next_id == 1


def test_memory_translation_rollback_hides_intermediate_state_from_observer_and_claimer():
    lock, articles, jobs, _store, article = _repositories()
    user_id = uuid4()
    at_failpoint = Event()
    release_failpoint = Event()
    translation_done = Event()
    observer_done = Event()
    claimer_done = Event()
    outcomes: dict[str, object] = {}

    def failpoint() -> None:
        at_failpoint.set()
        assert release_failpoint.wait(timeout=2)
        raise RuntimeError("forced rollback")

    store = MemoryTranslationEnqueueStore(
        articles,
        jobs,
        lock,
        before_article_update=failpoint,
    )

    def translate() -> None:
        try:
            store.enqueue(article.id, created_by=user_id)
        except RuntimeError as error:
            outcomes["translation_error"] = str(error)
        finally:
            translation_done.set()

    def observe() -> None:
        outcomes["article"] = articles.get_article(article.id)
        observer_done.set()

    def claim() -> None:
        outcomes["claimed"] = jobs.claim_next("worker")
        claimer_done.set()

    translation_thread = Thread(target=translate)
    translation_thread.start()
    assert at_failpoint.wait(timeout=2)

    observer_thread = Thread(target=observe)
    claimer_thread = Thread(target=claim)
    observer_thread.start()
    claimer_thread.start()
    assert not observer_done.wait(timeout=0.1)
    assert not claimer_done.wait(timeout=0.1)

    release_failpoint.set()
    assert translation_done.wait(timeout=2)
    assert observer_done.wait(timeout=2)
    assert claimer_done.wait(timeout=2)
    translation_thread.join(timeout=2)
    observer_thread.join(timeout=2)
    claimer_thread.join(timeout=2)

    assert outcomes["translation_error"] == "forced rollback"
    assert outcomes["article"].content_zh_status is None
    assert outcomes["claimed"] is None
    assert jobs._jobs == {}
    assert jobs._watchers_by_job == {}


def test_memory_translation_success_hides_intermediate_state_until_commit():
    lock, articles, jobs, _store, article = _repositories()
    user_id = uuid4()
    at_failpoint = Event()
    release_failpoint = Event()
    translation_done = Event()
    observer_done = Event()
    outcomes: dict[str, object] = {}

    def failpoint() -> None:
        at_failpoint.set()
        assert release_failpoint.wait(timeout=2)

    store = MemoryTranslationEnqueueStore(
        articles,
        jobs,
        lock,
        before_article_update=failpoint,
    )

    def translate() -> None:
        outcomes["result"] = store.enqueue(article.id, created_by=user_id)
        translation_done.set()

    def observe() -> None:
        outcomes["article"] = articles.get_article(article.id)
        observer_done.set()

    translation_thread = Thread(target=translate)
    translation_thread.start()
    assert at_failpoint.wait(timeout=2)
    observer_thread = Thread(target=observe)
    observer_thread.start()
    assert not observer_done.wait(timeout=0.1)

    release_failpoint.set()
    assert translation_done.wait(timeout=2)
    assert observer_done.wait(timeout=2)
    translation_thread.join(timeout=2)
    observer_thread.join(timeout=2)

    result = outcomes["result"]
    assert result.status == "queued"
    assert outcomes["article"].content_zh_status == "queued"
    assert result.job is not None
    assert jobs.get_visible_job(result.job.id, current_user_id=user_id, is_admin=False) is not None

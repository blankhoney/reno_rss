from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app import composition
from app.composition import (
    CompositionFactories,
    WorkerRuntimeSettings,
    build_handler_registry,
    close_queue,
)
from app.jobs.queue import InMemoryJobQueue, PostgresJobQueue


APPLICATION_FUNCTIONS = {
    "auto_score_candidates": "run_auto_score_candidates",
    "complete_ingest_cycle": "complete_ingest_cycle",
    "fetch_article_content": "fetch_article_content",
    "generate_daily_brief": "generate_daily_brief",
    "generate_recommendations": "generate_recommendations",
    "govern_sources": "govern_sources",
    "research_brief": "run_budgeted_research_brief",
    "run_benchmark": "run_benchmark",
    "score_batch": "score_batch",
    "sync_miniflux_entries": "run_sync_miniflux_entries",
    "translate_article": "translate_article",
}

EXPECTED_RESOURCE_COUNTS = {
    "auto_score_candidates": 1,
    "complete_ingest_cycle": 1,
    "fetch_article_content": 1,
    "generate_daily_brief": 1,
    "generate_recommendations": 1,
    "govern_sources": 1,
    "research_brief": 2,
    "run_benchmark": 1,
    "score_batch": 1,
    "sync_miniflux_entries": 1,
    "translate_article": 2,
}


class FakeResource:
    def __init__(self, *, dispose_error: BaseException | None = None):
        self.dispose_calls = 0
        self.dispose_error = dispose_error

    def dispose(self) -> None:
        self.dispose_calls += 1
        if self.dispose_error is not None:
            raise self.dispose_error


class FakeMinifluxClient:
    def __init__(self, exits: list[object]):
        self.exits = exits

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc, _traceback):
        self.exits.append(exc_type)
        return False


def runtime_settings(tmp_path: Path) -> WorkerRuntimeSettings:
    return WorkerRuntimeSettings(
        database_url="postgresql+psycopg://worker:test@localhost/worker",
        worker_id="test-worker",
        heartbeat_file=tmp_path / "heartbeat",
    )


def fake_factories(
    resources: list[FakeResource],
    client_exits: list[object],
) -> CompositionFactories:
    def resource_factory(*_args, **_kwargs):
        resource = FakeResource()
        resources.append(resource)
        return resource

    return CompositionFactories(
        score_sink=resource_factory,
        article_sink=resource_factory,
        brief_sink=resource_factory,
        research_sink=resource_factory,
        content_sink=resource_factory,
        usage_ledger=resource_factory,
        recommendation_sink=resource_factory,
        governance_sink=resource_factory,
        benchmark_sink=resource_factory,
        provider=object,
        miniflux_config=object,
        miniflux_client=lambda _config: FakeMinifluxClient(client_exits),
        external_content_provider=object,
        webhook_client=object,
    )


@pytest.mark.parametrize("job_type", APPLICATION_FUNCTIONS)
def test_each_database_handler_disposes_per_invocation_on_success(
    monkeypatch,
    tmp_path,
    job_type,
):
    resources: list[FakeResource] = []
    client_exits: list[object] = []
    monkeypatch.setattr(
        composition,
        APPLICATION_FUNCTIONS[job_type],
        lambda *_args, **_kwargs: {"ok": True},
    )
    registry = build_handler_registry(
        runtime_settings(tmp_path),
        factories=fake_factories(resources, client_exits),
    )

    assert registry[job_type]({}) == {"ok": True}
    assert len(resources) == EXPECTED_RESOURCE_COUNTS[job_type]
    assert all(resource.dispose_calls == 1 for resource in resources)
    if job_type in {"fetch_article_content", "sync_miniflux_entries"}:
        assert client_exits == [None]
    else:
        assert client_exits == []


@pytest.mark.parametrize("job_type", APPLICATION_FUNCTIONS)
def test_each_database_handler_disposes_per_invocation_on_failure(
    monkeypatch,
    tmp_path,
    job_type,
):
    resources: list[FakeResource] = []
    client_exits: list[object] = []

    def fail(*_args, **_kwargs):
        raise RuntimeError("job failed")

    monkeypatch.setattr(composition, APPLICATION_FUNCTIONS[job_type], fail)
    registry = build_handler_registry(
        runtime_settings(tmp_path),
        factories=fake_factories(resources, client_exits),
    )

    with pytest.raises(RuntimeError, match="job failed"):
        registry[job_type]({})
    assert len(resources) == EXPECTED_RESOURCE_COUNTS[job_type]
    assert all(resource.dispose_calls == 1 for resource in resources)
    if job_type in {"fetch_article_content", "sync_miniflux_entries"}:
        assert client_exits == [RuntimeError]
    else:
        assert client_exits == []


def test_handler_invocations_create_fresh_resources_and_providers(monkeypatch, tmp_path):
    resources: list[FakeResource] = []
    providers: list[object] = []

    def score_sink(_database_url):
        resource = FakeResource()
        resources.append(resource)
        return resource

    def provider():
        instance = object()
        providers.append(instance)
        return instance

    monkeypatch.setattr(
        composition,
        "score_batch",
        lambda *_args, **_kwargs: {"ok": True},
    )
    registry = build_handler_registry(
        runtime_settings(tmp_path),
        factories=CompositionFactories(
            score_sink=score_sink,
            provider=provider,
            webhook_client=object,
        ),
    )

    registry["score_batch"]({})
    registry["score_batch"]({})

    assert len(resources) == 2
    assert len(providers) == 2
    assert resources[0] is not resources[1]
    assert providers[0] is not providers[1]
    assert all(resource.dispose_calls == 1 for resource in resources)


def test_multi_resource_factory_failure_disposes_already_created_resource(tmp_path):
    first = FakeResource()

    def fail_ledger(_database_url):
        raise RuntimeError("ledger unavailable")

    factories = CompositionFactories(
        research_sink=lambda _database_url: first,
        usage_ledger=fail_ledger,
    )
    registry = build_handler_registry(runtime_settings(tmp_path), factories=factories)

    with pytest.raises(RuntimeError, match="ledger unavailable"):
        registry["research_brief"]({})
    assert first.dispose_calls == 1


def test_dispose_failure_does_not_replace_job_failure(monkeypatch, tmp_path):
    resource = FakeResource(dispose_error=RuntimeError("dispose failed"))

    def fail(*_args, **_kwargs):
        raise ValueError("job failed first")

    monkeypatch.setattr(composition, "score_batch", fail)
    registry = build_handler_registry(
        runtime_settings(tmp_path),
        factories=CompositionFactories(score_sink=lambda _database_url: resource),
    )

    with pytest.raises(ValueError, match="job failed first"):
        registry["score_batch"]({})
    assert resource.dispose_calls == 1


def test_handlers_keep_existing_missing_database_errors():
    registry = build_handler_registry(WorkerRuntimeSettings(database_url=None))

    with pytest.raises(
        RuntimeError,
        match="SCORING_DATABASE_URL is required for score_batch",
    ):
        registry["score_batch"]({})


def test_main_keeps_composition_compatibility_re_exports():
    main_module = importlib.import_module("app.main")

    assert main_module.normalize_database_url is composition.normalize_database_url
    assert main_module.create_worker_queue is composition.create_worker_queue
    assert main_module.build_handler_registry is composition.build_handler_registry


def test_close_queue_disposes_closable_and_ignores_in_memory_queue():
    closable = FakeResource()

    close_queue(closable)
    close_queue(InMemoryJobQueue())

    assert closable.dispose_calls == 1


def test_close_queue_disposes_postgres_queue_engine():
    class FakeEngine:
        def __init__(self):
            self.dispose_calls = 0

        def dispose(self):
            self.dispose_calls += 1

    engine = FakeEngine()
    queue = PostgresJobQueue(
        "postgresql+psycopg://worker:test@localhost/worker",
        engine=engine,
    )

    close_queue(queue)

    assert engine.dispose_calls == 1


def test_close_queue_rejects_non_callable_dispose():
    class InvalidQueue:
        dispose = "not callable"

    with pytest.raises(TypeError, match="dispose attribute must be callable"):
        close_queue(InvalidQueue())  # type: ignore[arg-type]


def test_main_disposes_queue_after_normal_return(monkeypatch, tmp_path):
    main_module = importlib.import_module("app.main")
    queue = FakeResource()
    settings = runtime_settings(tmp_path)

    class SettingsLoader:
        @classmethod
        def from_env(cls):
            return settings

    monkeypatch.setattr(main_module, "WorkerRuntimeSettings", SettingsLoader)
    monkeypatch.setattr(main_module, "create_worker_queue", lambda _settings: queue)
    monkeypatch.setattr(main_module, "build_handler_registry", lambda _settings: {})
    monkeypatch.setattr(main_module, "make_tick_callback", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(main_module, "run_forever", lambda *_args, **_kwargs: None)

    main_module.main()

    assert queue.dispose_calls == 1


def test_main_preserves_runtime_error_when_queue_dispose_fails(monkeypatch, tmp_path):
    main_module = importlib.import_module("app.main")
    queue = FakeResource(dispose_error=RuntimeError("dispose failed"))
    settings = runtime_settings(tmp_path)

    class SettingsLoader:
        @classmethod
        def from_env(cls):
            return settings

    def fail_runtime(*_args, **_kwargs):
        raise ValueError("runtime failed first")

    monkeypatch.setattr(main_module, "WorkerRuntimeSettings", SettingsLoader)
    monkeypatch.setattr(main_module, "create_worker_queue", lambda _settings: queue)
    monkeypatch.setattr(main_module, "build_handler_registry", lambda _settings: {})
    monkeypatch.setattr(main_module, "make_tick_callback", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(main_module, "run_forever", fail_runtime)

    with pytest.raises(ValueError, match="runtime failed first"):
        main_module.main()
    assert queue.dispose_calls == 1

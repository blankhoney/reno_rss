from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import (
    ApiError,
    get_auth_store,
    get_benchmark_repository,
    get_job_repository,
    get_scoring_repository,
    require_admin,
)
from app.core.budget import DailyCallBudget
from app.db.auth_store import DEMO_USER_DISPLAY_NAME, AuthStore, UserRecord
from app.db.repositories.benchmarks import BenchmarkRunRecord, BenchmarkStore
from app.db.repositories.jobs import JobStore, dedupe_key_for
from app.db.repositories.scoring import (
    ScoringBatchItemRecord,
    ScoringBatchRecord,
    ScoringStore,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateScoringBatchRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    candidate_window: str = Field(pattern="^(today|last_3_days|custom)$")
    article_ids: list[int] = Field(min_length=1, max_length=30)


class SyncMinifluxRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    after_entry_id: int | None = Field(default=None, ge=1)


class CreateBenchmarkRequest(BaseModel):
    suite: Literal["ranking", "model_swap", "db_perf"] = "ranking"
    mode: Literal["ci_mini", "manual_full"] = "ci_mini"
    provider: str = Field(default="mock", min_length=1, max_length=80)
    params: dict[str, object] = Field(default_factory=dict)
    confirm_real_llm: bool = False


def user_public(user: UserRecord) -> dict[str, object]:
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
        "is_demo": user.display_name == DEMO_USER_DISPLAY_NAME,
    }


def scoring_batch_item_public(item: ScoringBatchItemRecord) -> dict[str, object]:
    return {
        "id": item.id,
        "batch_id": item.batch_id,
        "article_id": item.article_id,
        "status": item.status,
        "base_score_id": item.base_score_id,
        "error": item.error,
    }


def scoring_batch_public(batch: ScoringBatchRecord) -> dict[str, object]:
    return {
        "id": batch.id,
        "name": batch.name,
        "status": batch.status,
        "trigger_type": batch.trigger_type,
        "candidate_window": batch.candidate_window,
        "article_count": batch.article_count,
        "created_by": str(batch.created_by) if batch.created_by else None,
        "created_at": batch.created_at.isoformat(),
        "started_at": batch.started_at.isoformat() if batch.started_at else None,
        "finished_at": batch.finished_at.isoformat() if batch.finished_at else None,
        "items": [scoring_batch_item_public(item) for item in batch.items],
    }


def benchmark_run_public(run: BenchmarkRunRecord) -> dict[str, object]:
    return {
        "id": run.id,
        "suite": run.suite,
        "mode": run.mode,
        "status": run.status,
        "params": run.params,
        "metrics": run.metrics,
        "artifact_path": run.artifact_path,
        "cost_estimate": run.cost_estimate,
        "created_by": str(run.created_by) if run.created_by else None,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/users")
async def list_users(
    _current_user: UserRecord = Depends(require_admin),
    auth_store: AuthStore = Depends(get_auth_store),
) -> dict[str, list[object]]:
    return {"items": [user_public(user) for user in auth_store.list_users()]}


@router.get("/usage/today")
def usage_today(
    request: Request,
    _current_user: UserRecord = Depends(require_admin),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, object]:
    """Admin cost cockpit: worker scores (DB) + API ask budget (process memory)."""
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    scores_today = scoring_repository.count_scores_since(day_start)
    budget = getattr(request.app.state, "llm_budget", None)
    if isinstance(budget, DailyCallBudget):
        ask_snapshot = budget.snapshot()
    else:
        ask_snapshot = {
            "used": 0,
            "limit": 0,
            "remaining": None,
            "day": day_start.date().isoformat(),
            "accounting": "unavailable",
        }
    return {
        "day": day_start.date().isoformat(),
        "scores": {
            "count_today": scores_today,
            "accounting": "database",
            "note": "Counts success and error score rows (each is one scoring attempt).",
        },
        "ask": {
            **ask_snapshot,
            "ask_accounting": ask_snapshot.get("accounting", "process_memory"),
            "note": "In-process counter; resets on API restart. Prefer MiniMax console for hard caps.",
        },
    }


@router.post("/daily-brief")
def enqueue_daily_brief(
    current_user: UserRecord = Depends(require_admin),
    job_repository: JobStore = Depends(get_job_repository),
) -> JSONResponse:
    job = job_repository.enqueue(
        "generate_daily_brief",
        {"limit": 10, "trigger": "admin"},
        dedupe_key=dedupe_key_for("generate_daily_brief", datetime.now(UTC).date().isoformat()),
        created_by=current_user.id,
    )
    return JSONResponse(
        status_code=202,
        content={"job_id": job.id, "job_type": job.job_type, "status": job.status},
    )


@router.post("/govern-sources")
def enqueue_govern_sources(
    current_user: UserRecord = Depends(require_admin),
    job_repository: JobStore = Depends(get_job_repository),
    dry_run: bool = False,
) -> JSONResponse:
    """Queue source-quality demotion pass (hide residual/failed feeds)."""
    job = job_repository.enqueue(
        "govern_sources",
        {
            "limit": 500,
            "min_samples": 5,
            "bad_ratio_threshold": 0.6,
            "dry_run": dry_run,
            "trigger": "admin",
        },
        dedupe_key=dedupe_key_for(
            "govern_sources",
            f"{datetime.now(UTC).date().isoformat()}:{'dry' if dry_run else 'apply'}",
        ),
        created_by=current_user.id,
    )
    return JSONResponse(
        status_code=202,
        content={"job_id": job.id, "job_type": job.job_type, "status": job.status},
    )


@router.post("/sync")
def enqueue_miniflux_sync(
    payload: SyncMinifluxRequest,
    current_user: UserRecord = Depends(require_admin),
    job_repository: JobStore = Depends(get_job_repository),
) -> JSONResponse:
    job_payload: dict[str, object] = {"limit": payload.limit}
    if payload.after_entry_id is not None:
        job_payload["after_entry_id"] = payload.after_entry_id
    job = job_repository.enqueue(
        "sync_miniflux_entries",
        job_payload,
        dedupe_key=dedupe_key_for("sync_miniflux_entries", "manual"),
        created_by=current_user.id,
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status,
        },
    )


@router.post("/scoring-batches")
def create_scoring_batch(
    payload: CreateScoringBatchRequest,
    response: Response,
    current_user: UserRecord = Depends(require_admin),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, object]:
    batch = scoring_repository.create_batch(
        name=payload.name,
        candidate_window=payload.candidate_window,
        article_ids=payload.article_ids,
        created_by=current_user.id,
    )
    response.status_code = 201
    return {"batch": scoring_batch_public(batch)}


@router.get("/scoring-batches/{batch_id}")
def get_scoring_batch(
    batch_id: int = Path(gt=0),
    _current_user: UserRecord = Depends(require_admin),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, object]:
    batch = scoring_repository.get_batch(batch_id)
    if batch is None:
        raise ApiError(404, "not_found", "Scoring batch not found")
    return {"batch": scoring_batch_public(batch)}


@router.post("/scoring-batches/{batch_id}/start")
def start_scoring_batch(
    batch_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_admin),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
    job_repository: JobStore = Depends(get_job_repository),
) -> JSONResponse:
    batch = scoring_repository.get_batch(batch_id)
    if batch is None:
        raise ApiError(404, "not_found", "Scoring batch not found")

    job = job_repository.enqueue(
        "score_batch",
        {"batch_id": batch_id},
        dedupe_key=dedupe_key_for("score_batch", batch_id),
        created_by=current_user.id,
    )
    return JSONResponse(
        status_code=202,
        content={"batch_id": batch_id, "job_id": job.id, "status": job.status},
    )


@router.post("/benchmarks", status_code=202)
def create_benchmark_run(
    payload: CreateBenchmarkRequest,
    current_user: UserRecord = Depends(require_admin),
    benchmark_repository: BenchmarkStore = Depends(get_benchmark_repository),
    job_repository: JobStore = Depends(get_job_repository),
) -> JSONResponse:
    if payload.suite == "model_swap":
        raise ApiError(400, "unsupported", "model_swap benchmark is not executable yet")
    if payload.provider != "mock" and not (
        payload.mode == "manual_full" and payload.confirm_real_llm
    ):
        raise ApiError(
            400,
            "real_llm_confirmation_required",
            "Real LLM benchmarks require manual_full mode and explicit confirmation",
        )

    run_params = dict(payload.params)
    run_params["provider"] = payload.provider
    run = benchmark_repository.create_run(
        suite=payload.suite,
        mode=payload.mode,
        params=run_params,
        created_by=current_user.id,
    )
    job_payload = {
        "benchmark_run_id": run.id,
        "suite": payload.suite,
        "mode": payload.mode,
        "provider": payload.provider,
        "params": payload.params,
    }
    job = job_repository.enqueue(
        "run_benchmark",
        job_payload,
        dedupe_key=dedupe_key_for("run_benchmark", run.id),
        created_by=current_user.id,
    )
    return JSONResponse(
        status_code=202,
        content={
            "benchmark_run": benchmark_run_public(run),
            "job": {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
            },
        },
    )


@router.get("/benchmarks/{benchmark_run_id}")
def get_benchmark_run(
    benchmark_run_id: int = Path(gt=0),
    _current_user: UserRecord = Depends(require_admin),
    benchmark_repository: BenchmarkStore = Depends(get_benchmark_repository),
) -> dict[str, object]:
    run = benchmark_repository.get_run(benchmark_run_id)
    if run is None:
        raise ApiError(404, "not_found", "Benchmark run not found")
    return {"benchmark_run": benchmark_run_public(run)}

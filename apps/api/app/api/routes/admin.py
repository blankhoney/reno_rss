from fastapi import APIRouter, Depends, Path, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import (
    ApiError,
    get_job_repository,
    get_scoring_repository,
    require_admin,
)
from app.db.auth_store import UserRecord
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


@router.get("/users")
async def list_users(_current_user: UserRecord = Depends(require_admin)) -> dict[str, list[object]]:
    return {"items": []}


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

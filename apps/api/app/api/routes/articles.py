from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse

from app.api.deps import get_job_repository, require_user
from app.db.auth_store import UserRecord
from app.db.repositories.jobs import JobStore, dedupe_key_for


router = APIRouter(prefix="/api", tags=["articles"])


@router.get("/articles")
async def list_articles(_current_user: UserRecord = Depends(require_user)) -> dict[str, list[object]]:
    return {"items": []}


@router.post("/articles/{article_id}/fetch-content")
def enqueue_fetch_content_job(
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    job_repository: JobStore = Depends(get_job_repository),
) -> JSONResponse:
    job = job_repository.enqueue(
        "fetch_article_content",
        {"article_id": article_id},
        dedupe_key=dedupe_key_for("fetch_article_content", article_id),
        created_by=current_user.id,
    )
    return JSONResponse(status_code=202, content={"job_id": job.id, "status": job.status})

from fastapi import APIRouter, Depends, Path

from app.api.deps import ApiError, get_job_repository, require_user
from app.db.auth_store import UserRecord
from app.db.repositories.jobs import JobRecord, JobStore


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def job_public(job: JobRecord) -> dict[str, object]:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/{job_id}")
def get_job(
    job_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    job_repository: JobStore = Depends(get_job_repository),
) -> dict[str, object]:
    job = job_repository.get_visible_job(
        job_id,
        current_user_id=current_user.id,
        is_admin=current_user.role == "admin",
    )
    if job is None:
        raise ApiError(404, "not_found", "Job not found")
    return job_public(job)

"""Corpus research agent jobs (GOAL §4.D). Poll status via GET /api/jobs/{id}."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.api.deps import ApiError, get_job_repository, require_user
from app.api.routes.jobs import job_public
from app.db.auth_store import UserRecord
from app.db.repositories.jobs import JobStore, dedupe_key_for


router = APIRouter(prefix="/api/research", tags=["research"])

RESEARCH_BRIEF_JOB_TYPE = "research_brief"


class ResearchJobRequest(BaseModel):
    scope: Literal["topn", "project", "topic"] = "topn"
    topic: str | None = Field(default=None, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    max_articles: int = Field(default=10, ge=1, le=30)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("question must not be empty")
        return text

    @field_validator("topic")
    @classmethod
    def strip_topic(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


@router.post("/jobs")
def enqueue_research_job(
    request: Request,
    payload: ResearchJobRequest,
    current_user: UserRecord = Depends(require_user),
    job_repository: JobStore = Depends(get_job_repository),
) -> JSONResponse:
    if payload.scope == "topic" and not payload.topic:
        raise ApiError(422, "unprocessable", "topic is required when scope=topic")

    ledger = getattr(request.app.state, "cost_ledger", None)
    if ledger is not None and hasattr(ledger, "can_charge"):
        try:
            if not ledger.can_charge("agent", 1):
                raise ApiError(429, "rate_limited", "Agent daily budget exceeded")
            ledger.charge("agent", 1)
        except RuntimeError as exc:
            raise ApiError(429, "rate_limited", str(exc)) from exc

    job_payload: dict[str, object] = {
        "scope": payload.scope,
        "question": payload.question,
        "max_articles": payload.max_articles,
        "user_id": str(current_user.id),
    }
    if payload.topic is not None:
        job_payload["topic"] = payload.topic

    # Dedupe per user + scope + question fingerprint so rapid double-clicks reuse one job.
    dedupe_seed = f"{current_user.id}:{payload.scope}:{payload.topic or ''}:{payload.question}"
    job = job_repository.enqueue(
        RESEARCH_BRIEF_JOB_TYPE,
        job_payload,
        dedupe_key=dedupe_key_for(RESEARCH_BRIEF_JOB_TYPE, dedupe_seed),
        created_by=current_user.id,
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            # Prefer polling the shared jobs surface; this alias stays for discoverability.
            "poll_url": f"/api/jobs/{job.id}",
        },
    )


@router.get("/jobs/{job_id}")
def get_research_job(
    job_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    job_repository: JobStore = Depends(get_job_repository),
) -> dict[str, object]:
    """Thin alias over /api/jobs/{id}; only returns research_brief jobs owned/visible to the user."""
    job = job_repository.get_visible_job(
        job_id,
        current_user_id=current_user.id,
        is_admin=current_user.role == "admin",
    )
    if job is None or job.job_type != RESEARCH_BRIEF_JOB_TYPE:
        raise ApiError(404, "not_found", "Research job not found")
    return job_public(job)

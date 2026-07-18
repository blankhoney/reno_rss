"""Shared project ACL API (GOAL §4.E)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import ApiError, get_project_acl_repository, require_user
from app.db.auth_store import UserRecord
from app.db.repositories.project_acl import ProjectAclStore
from app.domain.acl import ProjectRole, highest_role


router = APIRouter(prefix="/api/projects", tags=["acl"])


class GrantRequest(BaseModel):
    user_id: UUID
    role: str = Field(pattern="^(owner|editor|viewer)$")


@router.get("/{project_id}/acl")
def list_acl(
    project_id: str,
    current_user: UserRecord = Depends(require_user),
    repository: ProjectAclStore = Depends(get_project_acl_repository),
) -> dict[str, object]:
    grants = repository.list_grants(project_id)
    # Owner-or-self visibility: show grants if user has any role on project or list empty owner seed.
    role = highest_role(grants, user_id=current_user.id, project_id=project_id)
    if grants and role is None:
        raise ApiError(403, "forbidden", "Not a member of this project")
    return {
        "project_id": project_id,
        "items": [
            {
                "user_id": str(grant.user_id),
                "role": grant.role.value,
            }
            for grant in grants
        ],
        "my_role": role.value if role else None,
    }


@router.put("/{project_id}/acl")
def put_acl(
    project_id: str,
    body: GrantRequest,
    current_user: UserRecord = Depends(require_user),
    repository: ProjectAclStore = Depends(get_project_acl_repository),
) -> dict[str, object]:
    try:
        grants = repository.grant(
            project_id,
            actor_user_id=current_user.id,
            target_user_id=body.user_id,
            role=ProjectRole(body.role),
        )
    except PermissionError as exc:
        raise ApiError(403, "forbidden", str(exc)) from exc
    return {
        "project_id": project_id,
        "items": [
            {"user_id": str(grant.user_id), "role": grant.role.value} for grant in grants
        ],
    }

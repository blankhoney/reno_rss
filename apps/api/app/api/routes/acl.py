"""Shared project ACL API (GOAL §4.E)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import ApiError, require_user
from app.db.auth_store import UserRecord
from app.domain.acl import ProjectGrant, ProjectRole, authorize, highest_role


router = APIRouter(prefix="/api/projects", tags=["acl"])


class GrantRequest(BaseModel):
    user_id: UUID
    role: str = Field(pattern="^(owner|editor|viewer)$")


def _store(request: Request) -> dict[str, list[ProjectGrant]]:
    store = getattr(request.app.state, "project_acl_grants", None)
    if store is None:
        store = {}
        request.app.state.project_acl_grants = store
    return store


@router.get("/{project_id}/acl")
def list_acl(
    project_id: str,
    request: Request,
    current_user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    grants = list(_store(request).get(project_id, []))
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
    request: Request,
    current_user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    store = _store(request)
    grants = list(store.get(project_id, []))
    if not grants:
        # First grant: current user becomes owner and can add others.
        grants = [
            ProjectGrant(project_id=project_id, user_id=current_user.id, role=ProjectRole.OWNER)
        ]
    if not authorize(
        grants,
        user_id=current_user.id,
        project_id=project_id,
        need=ProjectRole.OWNER,
    ):
        raise ApiError(403, "forbidden", "Only project owner can manage ACL")
    role = ProjectRole(body.role)
    grants = [grant for grant in grants if not (grant.user_id == body.user_id)]
    grants.append(ProjectGrant(project_id=project_id, user_id=body.user_id, role=role))
    store[project_id] = grants
    return {
        "project_id": project_id,
        "items": [
            {"user_id": str(grant.user_id), "role": grant.role.value} for grant in grants
        ],
    }

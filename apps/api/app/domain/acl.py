"""Lightweight shared-project ACL model (GOAL §4.E multi-user capability).

Default single-user quality is unchanged: missing grants mean only the owner
can access a project workspace. This module is pure policy — storage lives in
repositories when wired.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class ProjectRole(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


ROLE_RANK = {
    ProjectRole.VIEWER: 1,
    ProjectRole.EDITOR: 2,
    ProjectRole.OWNER: 3,
}


@dataclass(frozen=True)
class ProjectGrant:
    project_id: str
    user_id: UUID
    role: ProjectRole


def can_read(role: ProjectRole | None) -> bool:
    return role is not None


def can_edit(role: ProjectRole | None) -> bool:
    return role in {ProjectRole.OWNER, ProjectRole.EDITOR}


def can_manage(role: ProjectRole | None) -> bool:
    return role == ProjectRole.OWNER


def highest_role(grants: Iterable[ProjectGrant], *, user_id: UUID, project_id: str) -> ProjectRole | None:
    best: ProjectRole | None = None
    for grant in grants:
        if grant.user_id != user_id or grant.project_id != project_id:
            continue
        if best is None or ROLE_RANK[grant.role] > ROLE_RANK[best]:
            best = grant.role
    return best


def authorize(
    grants: Iterable[ProjectGrant],
    *,
    user_id: UUID,
    project_id: str,
    need: ProjectRole,
) -> bool:
    role = highest_role(grants, user_id=user_id, project_id=project_id)
    if role is None:
        return False
    return ROLE_RANK[role] >= ROLE_RANK[need]

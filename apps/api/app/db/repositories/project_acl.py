"""Persistent storage for shared-project ACL grants.

The API uses the same repository contract in local tests and Postgres-backed
deployments. Postgres grants are serialized per project so concurrent first
writes cannot accidentally create multiple bootstrap owners.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import project_acl_grants
from app.domain.acl import ProjectGrant, ProjectRole, authorize


class ProjectAclStore(Protocol):
    def list_grants(self, project_id: str) -> list[ProjectGrant]: ...

    def grant(
        self,
        project_id: str,
        *,
        actor_user_id: UUID,
        target_user_id: UUID,
        role: ProjectRole,
    ) -> list[ProjectGrant]: ...


class MemoryProjectAclRepository:
    """Process-local repository used only when no database is configured."""

    def __init__(self) -> None:
        self._grants: dict[str, list[ProjectGrant]] = {}

    def list_grants(self, project_id: str) -> list[ProjectGrant]:
        return list(self._grants.get(project_id, []))

    def grant(
        self,
        project_id: str,
        *,
        actor_user_id: UUID,
        target_user_id: UUID,
        role: ProjectRole,
    ) -> list[ProjectGrant]:
        grants = self.list_grants(project_id)
        if not grants:
            grants.append(
                ProjectGrant(
                    project_id=project_id,
                    user_id=actor_user_id,
                    role=ProjectRole.OWNER,
                )
            )
        if not authorize(
            grants,
            user_id=actor_user_id,
            project_id=project_id,
            need=ProjectRole.OWNER,
        ):
            raise PermissionError("Only project owner can manage ACL")
        grants = [grant for grant in grants if grant.user_id != target_user_id]
        grants.append(
            ProjectGrant(project_id=project_id, user_id=target_user_id, role=role)
        )
        self._grants[project_id] = grants
        return list(grants)


class DatabaseProjectAclRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def list_grants(self, project_id: str) -> list[ProjectGrant]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(project_acl_grants)
                    .where(project_acl_grants.c.project_id == project_id)
                    .order_by(project_acl_grants.c.id.asc())
                )
                .mappings()
                .all()
            )
        return [_grant_from_row(row) for row in rows]

    def grant(
        self,
        project_id: str,
        *,
        actor_user_id: UUID,
        target_user_id: UUID,
        role: ProjectRole,
    ) -> list[ProjectGrant]:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            # The table has no project parent row to lock. A transaction-scoped
            # advisory lock gives each project a stable first-owner boundary.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:project_id, 0))"),
                {"project_id": project_id},
            )
            rows = (
                connection.execute(
                    select(project_acl_grants)
                    .where(project_acl_grants.c.project_id == project_id)
                    .order_by(project_acl_grants.c.id.asc())
                )
                .mappings()
                .all()
            )
            grants = [_grant_from_row(row) for row in rows]
            if not grants:
                connection.execute(
                    project_acl_grants.insert().values(
                        project_id=project_id,
                        user_id=actor_user_id,
                        role=ProjectRole.OWNER.value,
                        created_at=now,
                    )
                )
                grants.append(
                    ProjectGrant(
                        project_id=project_id,
                        user_id=actor_user_id,
                        role=ProjectRole.OWNER,
                    )
                )
            if not authorize(
                grants,
                user_id=actor_user_id,
                project_id=project_id,
                need=ProjectRole.OWNER,
            ):
                raise PermissionError("Only project owner can manage ACL")
            connection.execute(
                pg_insert(project_acl_grants)
                .values(
                    project_id=project_id,
                    user_id=target_user_id,
                    role=role.value,
                    created_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[
                        project_acl_grants.c.project_id,
                        project_acl_grants.c.user_id,
                    ],
                    set_={"role": role.value},
                )
            )
            stored_rows = (
                connection.execute(
                    select(project_acl_grants)
                    .where(project_acl_grants.c.project_id == project_id)
                    .order_by(project_acl_grants.c.id.asc())
                )
                .mappings()
                .all()
            )
        return [_grant_from_row(row) for row in stored_rows]

    def dispose(self) -> None:
        self.engine.dispose()


def create_project_acl_repository(database_url: str | None) -> ProjectAclStore:
    if database_url:
        return DatabaseProjectAclRepository(database_url)
    return MemoryProjectAclRepository()


def _grant_from_row(row: object) -> ProjectGrant:
    return ProjectGrant(
        project_id=str(row["project_id"]),
        user_id=UUID(str(row["user_id"])),
        role=ProjectRole(str(row["role"])),
    )

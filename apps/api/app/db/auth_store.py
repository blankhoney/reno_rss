from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, select, update

from app.core.security import hash_token, new_recovery_code, new_token
from app.db.models import app_users


SESSION_TTL = timedelta(days=30)

# Reserved display name for the shared anonymous demo user (staging only).
DEMO_USER_DISPLAY_NAME = "__demo__"


@dataclass
class UserRecord:
    id: UUID
    display_name: str
    session_token_hash: str
    recovery_code_hash: str
    role: str
    session_expires_at: datetime
    recovery_rotated_at: datetime
    created_at: datetime
    last_seen_at: datetime | None = None


class AuthStore(Protocol):
    def login(
        self,
        display_name: str,
        current_session_token: str | None = None,
    ) -> tuple[UserRecord, str, str | None]: ...

    def recover(self, recovery_code: str) -> tuple[UserRecord, str, str] | None: ...

    def logout(self, session_token: str | None) -> None: ...

    def get_user_by_session(self, session_token: str | None) -> UserRecord | None: ...

    def create_user(self, display_name: str, role: str = "user") -> tuple[UserRecord, str, str]: ...

    def get_or_create_demo_user(self) -> UserRecord: ...

    def admin_exists(self) -> bool: ...


class MemoryAuthStore:
    def __init__(self) -> None:
        self._users_by_id: dict[UUID, UserRecord] = {}
        self._user_ids_by_session_hash: dict[str, UUID] = {}
        self._user_ids_by_recovery_hash: dict[str, UUID] = {}

    def login(
        self,
        display_name: str,
        current_session_token: str | None = None,
    ) -> tuple[UserRecord, str, str | None]:
        now = datetime.now(UTC)
        user = self.get_user_by_session(current_session_token)
        session_token = new_token()

        if user is not None:
            self._drop_session_hash(user.session_token_hash)
            user.display_name = display_name
            user.session_token_hash = hash_token(session_token)
            user.session_expires_at = now + SESSION_TTL
            user.last_seen_at = now
            self._user_ids_by_session_hash[user.session_token_hash] = user.id
            return user, session_token, None

        return self.create_user(display_name=display_name, role="user")

    def create_user(self, display_name: str, role: str = "user") -> tuple[UserRecord, str, str]:
        now = datetime.now(UTC)
        session_token = new_token()
        recovery_code = new_recovery_code()
        user = UserRecord(
            id=uuid4(),
            display_name=display_name,
            session_token_hash=hash_token(session_token),
            recovery_code_hash=hash_token(recovery_code),
            role=role,
            session_expires_at=now + SESSION_TTL,
            recovery_rotated_at=now,
            created_at=now,
            last_seen_at=now,
        )
        self._users_by_id[user.id] = user
        self._user_ids_by_session_hash[user.session_token_hash] = user.id
        self._user_ids_by_recovery_hash[user.recovery_code_hash] = user.id
        return user, session_token, recovery_code

    def get_or_create_demo_user(self) -> UserRecord:
        for user in sorted(self._users_by_id.values(), key=lambda u: u.created_at):
            if user.display_name == DEMO_USER_DISPLAY_NAME:
                return user
        user, _, _ = self.create_user(display_name=DEMO_USER_DISPLAY_NAME, role="user")
        return user

    def admin_exists(self) -> bool:
        return any(user.role == "admin" for user in self._users_by_id.values())

    def recover(self, recovery_code: str) -> tuple[UserRecord, str, str] | None:
        recovery_hash = hash_token(recovery_code)
        user_id = self._user_ids_by_recovery_hash.get(recovery_hash)
        if user_id is None:
            return None

        user = self._users_by_id[user_id]
        now = datetime.now(UTC)
        session_token = new_token()
        new_code = new_recovery_code()

        self._drop_session_hash(user.session_token_hash)
        self._user_ids_by_recovery_hash.pop(user.recovery_code_hash, None)
        user.session_token_hash = hash_token(session_token)
        user.recovery_code_hash = hash_token(new_code)
        user.session_expires_at = now + SESSION_TTL
        user.recovery_rotated_at = now
        user.last_seen_at = now
        self._user_ids_by_session_hash[user.session_token_hash] = user.id
        self._user_ids_by_recovery_hash[user.recovery_code_hash] = user.id
        return user, session_token, new_code

    def logout(self, session_token: str | None) -> None:
        user = self.get_user_by_session(session_token)
        if user is None:
            return
        self._drop_session_hash(user.session_token_hash)
        user.session_token_hash = hash_token(new_token())
        user.session_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    def get_user_by_session(self, session_token: str | None) -> UserRecord | None:
        if not session_token:
            return None
        session_hash = hash_token(session_token)
        user_id = self._user_ids_by_session_hash.get(session_hash)
        if user_id is None:
            return None
        user = self._users_by_id[user_id]
        if user.session_expires_at <= datetime.now(UTC):
            self._drop_session_hash(user.session_token_hash)
            return None
        user.last_seen_at = datetime.now(UTC)
        return user

    def _drop_session_hash(self, session_hash: str) -> None:
        if session_hash:
            self._user_ids_by_session_hash.pop(session_hash, None)


class DatabaseAuthStore:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def login(
        self,
        display_name: str,
        current_session_token: str | None = None,
    ) -> tuple[UserRecord, str, str | None]:
        user = self.get_user_by_session(current_session_token)
        if user is None:
            return self.create_user(display_name=display_name, role="user")

        now = datetime.now(UTC)
        session_token = new_token()
        session_hash = hash_token(session_token)
        values = {
            "display_name": display_name,
            "session_token_hash": session_hash,
            "session_expires_at": now + SESSION_TTL,
            "last_seen_at": now,
        }
        with self.engine.begin() as connection:
            row = connection.execute(
                update(app_users)
                .where(app_users.c.id == user.id)
                .values(**values)
                .returning(app_users)
            ).mappings().one()
        return _user_from_row(row), session_token, None

    def create_user(self, display_name: str, role: str = "user") -> tuple[UserRecord, str, str]:
        now = datetime.now(UTC)
        session_token = new_token()
        recovery_code = new_recovery_code()
        values = {
            "display_name": display_name,
            "session_token_hash": hash_token(session_token),
            "recovery_code_hash": hash_token(recovery_code),
            "role": role,
            "session_expires_at": now + SESSION_TTL,
            "recovery_rotated_at": now,
            "last_seen_at": now,
        }
        with self.engine.begin() as connection:
            row = (
                connection.execute(app_users.insert().values(**values).returning(app_users))
                .mappings()
                .one()
            )
        return _user_from_row(row), session_token, recovery_code

    def get_or_create_demo_user(self) -> UserRecord:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(app_users)
                    .where(app_users.c.display_name == DEMO_USER_DISPLAY_NAME)
                    .order_by(app_users.c.created_at.asc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
        if row is not None:
            return _user_from_row(row)
        user, _, _ = self.create_user(display_name=DEMO_USER_DISPLAY_NAME, role="user")
        return user

    def admin_exists(self) -> bool:
        with self.engine.begin() as connection:
            admin_id = connection.execute(
                select(app_users.c.id).where(app_users.c.role == "admin").limit(1)
            ).scalar_one_or_none()
        return admin_id is not None

    def recover(self, recovery_code: str) -> tuple[UserRecord, str, str] | None:
        recovery_hash = hash_token(recovery_code)
        now = datetime.now(UTC)
        session_token = new_token()
        new_code = new_recovery_code()
        values = {
            "session_token_hash": hash_token(session_token),
            "recovery_code_hash": hash_token(new_code),
            "session_expires_at": now + SESSION_TTL,
            "recovery_rotated_at": now,
            "last_seen_at": now,
        }
        with self.engine.begin() as connection:
            row = connection.execute(
                update(app_users)
                .where(app_users.c.recovery_code_hash == recovery_hash)
                .values(**values)
                .returning(app_users)
            ).mappings().one_or_none()
            if row is None:
                return None
        return _user_from_row(row), session_token, new_code

    def logout(self, session_token: str | None) -> None:
        user = self.get_user_by_session(session_token)
        if user is None:
            return

        with self.engine.begin() as connection:
            connection.execute(
                update(app_users)
                .where(app_users.c.id == user.id)
                .values(
                    session_token_hash=hash_token(new_token()),
                    session_expires_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )

    def get_user_by_session(self, session_token: str | None) -> UserRecord | None:
        if not session_token:
            return None

        now = datetime.now(UTC)
        session_hash = hash_token(session_token)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(app_users).where(
                        app_users.c.session_token_hash == session_hash,
                        app_users.c.session_expires_at > now,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            connection.execute(
                update(app_users)
                .where(app_users.c.id == row["id"])
                .values(last_seen_at=now)
            )
        return _user_from_row(row)

    def dispose(self) -> None:
        self.engine.dispose()


def create_auth_store(database_url: str | None) -> AuthStore:
    if database_url:
        return DatabaseAuthStore(database_url)
    return MemoryAuthStore()


def _user_from_row(row) -> UserRecord:
    return UserRecord(
        id=row["id"],
        display_name=row["display_name"],
        session_token_hash=row["session_token_hash"],
        recovery_code_hash=row["recovery_code_hash"],
        role=row["role"],
        session_expires_at=row["session_expires_at"],
        recovery_rotated_at=row["recovery_rotated_at"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
    )

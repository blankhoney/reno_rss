from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from typing import TextIO

from app.core.config import get_settings
from app.db.auth_store import AuthStore, UserRecord, create_auth_store


class AdminAlreadyExists(RuntimeError):
    """Raised when create-admin would silently create a duplicate admin."""


@dataclass(frozen=True)
class SeedResult:
    created: bool
    user: UserRecord | None
    recovery_code: str | None


def create_admin(
    auth_store: AuthStore,
    *,
    display_name: str,
    if_missing: bool = False,
) -> SeedResult:
    if auth_store.admin_exists():
        if if_missing:
            return SeedResult(created=False, user=None, recovery_code=None)
        raise AdminAlreadyExists("an admin user already exists")

    user, _session_token, recovery_code = auth_store.create_user(
        display_name=display_name,
        role="admin",
    )
    return SeedResult(created=True, user=user, recovery_code=recovery_code)


def print_seed_result(result: SeedResult, *, stream: TextIO = sys.stdout) -> None:
    if not result.created:
        print("admin_exists=true", file=stream)
        return

    if result.user is None or result.recovery_code is None:
        raise ValueError("created seed result must include user and recovery code")

    print(f"admin_id={result.user.id}", file=stream)
    print("role=admin", file=stream)
    print(f"recovery_code={result.recovery_code}", file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed AI Reader operational data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin_parser = subparsers.add_parser("create-admin", help="Create the first admin user.")
    create_admin_parser.add_argument("--display-name", required=True)
    create_admin_parser.add_argument(
        "--if-missing",
        action="store_true",
        help="Exit successfully without printing a recovery code if an admin already exists.",
    )

    args = parser.parse_args(argv)
    settings = get_settings()
    if settings.database_url is None:
        parser.error("SCORING_DATABASE_URL is required for seed commands")

    auth_store = create_auth_store(settings.database_url)
    try:
        if args.command == "create-admin":
            result = create_admin(
                auth_store,
                display_name=args.display_name,
                if_missing=args.if_missing,
            )
            print_seed_result(result)
            return 0
    except AdminAlreadyExists:
        print(
            "admin already exists; use --if-missing to treat this as success",
            file=sys.stderr,
        )
        return 2
    finally:
        dispose = getattr(auth_store, "dispose", None)
        if dispose is not None:
            dispose()

    parser.error(f"unknown seed command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

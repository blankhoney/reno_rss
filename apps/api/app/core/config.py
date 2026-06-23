import os
from dataclasses import dataclass


APP_VERSION = "0.4.0"


@dataclass(frozen=True)
class Settings:
    app_version: str = APP_VERSION
    database_url: str | None = None
    csrf_allowed_origins: set[str] | None = None


def _parse_csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().rstrip("/") for item in value.split(",") if item.strip()}


def normalize_database_url(database_url: str | None) -> str | None:
    if database_url is None:
        return None
    if database_url.startswith("postgres://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    return database_url


def get_settings() -> Settings:
    return Settings(
        database_url=normalize_database_url(os.environ.get("SCORING_DATABASE_URL")),
        csrf_allowed_origins=_parse_csv_set(os.environ.get("AI_READER_CSRF_ALLOWED_ORIGINS")),
    )

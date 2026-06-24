import os
from dataclasses import dataclass


APP_VERSION = "0.4.0"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Settings:
    app_version: str = APP_VERSION
    database_url: str | None = None
    csrf_allowed_origins: set[str] | None = None
    llm_provider: str = "mock"
    minimax_api_key: str = ""
    minimax_base_url: str = DEFAULT_MINIMAX_BASE_URL
    minimax_model: str = DEFAULT_MINIMAX_MODEL
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS


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


def _parse_float(value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    return float(value)


def get_settings() -> Settings:
    return Settings(
        database_url=normalize_database_url(os.environ.get("SCORING_DATABASE_URL")),
        csrf_allowed_origins=_parse_csv_set(os.environ.get("AI_READER_CSRF_ALLOWED_ORIGINS")),
        llm_provider=os.environ.get("LLM_PROVIDER", "mock"),
        minimax_api_key=os.environ.get("MINIMAX_API_KEY", ""),
        minimax_base_url=os.environ.get(
            "MINIMAX_BASE_URL",
            DEFAULT_MINIMAX_BASE_URL,
        ).rstrip("/"),
        minimax_model=os.environ.get("MINIMAX_MODEL", DEFAULT_MINIMAX_MODEL),
        llm_timeout_seconds=_parse_float(
            os.environ.get("LLM_TIMEOUT_SECONDS"),
            DEFAULT_LLM_TIMEOUT_SECONDS,
        ),
    )

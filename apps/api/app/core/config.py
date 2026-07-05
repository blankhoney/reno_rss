import os
from dataclasses import dataclass


APP_VERSION = "0.4.0"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0
DEFAULT_API_RATELIMIT = "120/minute"
DEFAULT_LLM_RATELIMIT = "5/minute;100/day"
DEFAULT_WRITE_RATELIMIT = "30/minute"
DEFAULT_AUTH_RATELIMIT = "5/minute;30/hour"
DEFAULT_LLM_DAILY_CALL_BUDGET = 500


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
    api_ratelimit_default: str = DEFAULT_API_RATELIMIT
    llm_ratelimit: str = DEFAULT_LLM_RATELIMIT
    write_ratelimit: str = DEFAULT_WRITE_RATELIMIT
    auth_ratelimit: str = DEFAULT_AUTH_RATELIMIT
    # In-memory API-process budget for direct ask calls. Worker LLM calls are
    # guarded separately by scheduler caps and operator-side provider limits.
    llm_daily_call_budget: int = DEFAULT_LLM_DAILY_CALL_BUDGET
    # When true, requests without a session cookie are resolved to a shared demo
    # user (role=user) so staging can be a fully public functional demo. MUST stay
    # False in production — only the staging compose overlay enables it.
    anonymous_demo_user_enabled: bool = False


def _parse_csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip().rstrip("/") for item in value.split(",") if item.strip()}


def _parse_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


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


def _parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


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
        api_ratelimit_default=os.environ.get("API_RATELIMIT_DEFAULT", DEFAULT_API_RATELIMIT),
        llm_ratelimit=os.environ.get("LLM_RATELIMIT", DEFAULT_LLM_RATELIMIT),
        write_ratelimit=os.environ.get("WRITE_RATELIMIT", DEFAULT_WRITE_RATELIMIT),
        auth_ratelimit=os.environ.get("AUTH_RATELIMIT", DEFAULT_AUTH_RATELIMIT),
        llm_daily_call_budget=_parse_int(
            os.environ.get("LLM_DAILY_CALL_BUDGET"),
            DEFAULT_LLM_DAILY_CALL_BUDGET,
        ),
        anonymous_demo_user_enabled=_parse_bool(
            os.environ.get("AI_READER_ANONYMOUS_DEMO")
        ),
    )

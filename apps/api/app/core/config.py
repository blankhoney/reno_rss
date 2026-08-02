import os
from dataclasses import dataclass


APP_VERSION = "0.4.0"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"
DEFAULT_MINIMAX_TEMPERATURE = 0.2
DEFAULT_MINIMAX_TOP_P = 0.9
DEFAULT_MINIMAX_MAX_COMPLETION_TOKENS = 16_384
DEFAULT_MINIMAX_REASONING_SPLIT = True
DEFAULT_MINIMAX_THINKING_TYPE = "disabled"
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0
DEFAULT_LOCAL_LLM_BASE_URL = "http://host.docker.internal:11434/v1"
DEFAULT_LOCAL_LLM_MODEL = "llama3.2"
DEFAULT_LOCAL_LLM_API_KEY = "local"
DEFAULT_API_RATELIMIT = "120/minute"
DEFAULT_LLM_RATELIMIT = "5/minute;100/day"
DEFAULT_WRITE_RATELIMIT = "30/minute"
DEFAULT_AUTH_RATELIMIT = "5/minute;30/hour"
DEFAULT_LLM_DAILY_CALL_BUDGET = 500
DEFAULT_SCORE_DAILY_CALL_BUDGET = 60
DEFAULT_AGENT_DAILY_CALL_BUDGET = 20
DEFAULT_TRANSLATION_DAILY_CALL_BUDGET = 60
DEFAULT_SLOW_REQUEST_MS = 500


@dataclass(frozen=True)
class Settings:
    app_version: str = APP_VERSION
    database_url: str | None = None
    csrf_allowed_origins: set[str] | None = None
    llm_provider: str = "mock"
    minimax_api_key: str = ""
    minimax_base_url: str = DEFAULT_MINIMAX_BASE_URL
    minimax_model: str = DEFAULT_MINIMAX_MODEL
    minimax_temperature: float = DEFAULT_MINIMAX_TEMPERATURE
    minimax_top_p: float = DEFAULT_MINIMAX_TOP_P
    minimax_max_completion_tokens: int | None = DEFAULT_MINIMAX_MAX_COMPLETION_TOKENS
    minimax_reasoning_split: bool = DEFAULT_MINIMAX_REASONING_SPLIT
    minimax_thinking_type: str | None = DEFAULT_MINIMAX_THINKING_TYPE
    local_llm_api_key: str = DEFAULT_LOCAL_LLM_API_KEY
    local_llm_base_url: str = DEFAULT_LOCAL_LLM_BASE_URL
    local_llm_model: str = DEFAULT_LOCAL_LLM_MODEL
    local_llm_temperature: float = DEFAULT_MINIMAX_TEMPERATURE
    local_llm_top_p: float = DEFAULT_MINIMAX_TOP_P
    local_llm_max_completion_tokens: int | None = DEFAULT_MINIMAX_MAX_COMPLETION_TOKENS
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    api_ratelimit_default: str = DEFAULT_API_RATELIMIT
    llm_ratelimit: str = DEFAULT_LLM_RATELIMIT
    write_ratelimit: str = DEFAULT_WRITE_RATELIMIT
    auth_ratelimit: str = DEFAULT_AUTH_RATELIMIT
    slow_request_ms: int = DEFAULT_SLOW_REQUEST_MS
    # Per-account database budgets. Score attempts remain independently
    # auditable from article_base_scores and worker-side caps.
    llm_daily_call_budget: int = DEFAULT_LLM_DAILY_CALL_BUDGET
    score_daily_call_budget: int = DEFAULT_SCORE_DAILY_CALL_BUDGET
    agent_daily_call_budget: int = DEFAULT_AGENT_DAILY_CALL_BUDGET
    translation_daily_call_budget: int = DEFAULT_TRANSLATION_DAILY_CALL_BUDGET
    scheduler_enabled: bool = True
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


# Keep these LLM env parsers in parity with apps/worker/app/providers/llm.py.
# The API image builds from apps/api only, so a shared package is not worth the
# build-context churn; tests/test_llm_env_parity.py locks the duplicated behavior.
def _parse_bool_with_default(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(database_url: str | None) -> str | None:
    # Keep in parity with apps/worker/app/main.py; both sides have golden tests.
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


def _parse_optional_positive_int(value: str | None, default: int | None) -> int | None:
    if value is None or not value.strip():
        return default
    parsed = int(value)
    return parsed if parsed > 0 else None


def _parse_optional_choice(
    value: str | None,
    default: str | None,
    choices: set[str],
) -> str | None:
    raw = default if value is None else value.strip().lower()
    if not raw:
        return None
    if raw not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"value must be one of: {allowed}")
    return raw


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
        minimax_temperature=_parse_float(
            os.environ.get("MINIMAX_TEMPERATURE"),
            DEFAULT_MINIMAX_TEMPERATURE,
        ),
        minimax_top_p=_parse_float(
            os.environ.get("MINIMAX_TOP_P"),
            DEFAULT_MINIMAX_TOP_P,
        ),
        minimax_max_completion_tokens=_parse_optional_positive_int(
            os.environ.get("MINIMAX_MAX_COMPLETION_TOKENS"),
            DEFAULT_MINIMAX_MAX_COMPLETION_TOKENS,
        ),
        minimax_reasoning_split=_parse_bool_with_default(
            os.environ.get("MINIMAX_REASONING_SPLIT"),
            DEFAULT_MINIMAX_REASONING_SPLIT,
        ),
        minimax_thinking_type=_parse_optional_choice(
            os.environ.get("MINIMAX_THINKING_TYPE"),
            DEFAULT_MINIMAX_THINKING_TYPE,
            {"adaptive", "disabled"},
        ),
        local_llm_api_key=os.environ.get("LOCAL_LLM_API_KEY", DEFAULT_LOCAL_LLM_API_KEY),
        local_llm_base_url=os.environ.get(
            "LOCAL_LLM_BASE_URL",
            DEFAULT_LOCAL_LLM_BASE_URL,
        ).rstrip("/"),
        local_llm_model=os.environ.get("LOCAL_LLM_MODEL", DEFAULT_LOCAL_LLM_MODEL),
        local_llm_temperature=_parse_float(
            os.environ.get("LOCAL_LLM_TEMPERATURE"),
            DEFAULT_MINIMAX_TEMPERATURE,
        ),
        local_llm_top_p=_parse_float(
            os.environ.get("LOCAL_LLM_TOP_P"),
            DEFAULT_MINIMAX_TOP_P,
        ),
        local_llm_max_completion_tokens=_parse_optional_positive_int(
            os.environ.get("LOCAL_LLM_MAX_COMPLETION_TOKENS"),
            DEFAULT_MINIMAX_MAX_COMPLETION_TOKENS,
        ),
        llm_timeout_seconds=_parse_float(
            os.environ.get("LLM_TIMEOUT_SECONDS"),
            DEFAULT_LLM_TIMEOUT_SECONDS,
        ),
        api_ratelimit_default=os.environ.get("API_RATELIMIT_DEFAULT", DEFAULT_API_RATELIMIT),
        llm_ratelimit=os.environ.get("LLM_RATELIMIT", DEFAULT_LLM_RATELIMIT),
        write_ratelimit=os.environ.get("WRITE_RATELIMIT", DEFAULT_WRITE_RATELIMIT),
        auth_ratelimit=os.environ.get("AUTH_RATELIMIT", DEFAULT_AUTH_RATELIMIT),
        slow_request_ms=_parse_int(
            os.environ.get("SLOW_REQUEST_MS"),
            DEFAULT_SLOW_REQUEST_MS,
        ),
        llm_daily_call_budget=_parse_int(
            os.environ.get("LLM_DAILY_CALL_BUDGET"),
            DEFAULT_LLM_DAILY_CALL_BUDGET,
        ),
        score_daily_call_budget=_parse_int(
            os.environ.get("SCHEDULE_SCORE_DAILY_ARTICLE_CAP"),
            DEFAULT_SCORE_DAILY_CALL_BUDGET,
        ),
        agent_daily_call_budget=_parse_int(
            os.environ.get("AGENT_DAILY_CALL_BUDGET"),
            DEFAULT_AGENT_DAILY_CALL_BUDGET,
        ),
        translation_daily_call_budget=_parse_int(
            os.environ.get("TRANSLATION_DAILY_CALL_BUDGET"),
            DEFAULT_TRANSLATION_DAILY_CALL_BUDGET,
        ),
        scheduler_enabled=_parse_bool_with_default(
            os.environ.get("SCHEDULER_ENABLED"),
            True,
        ),
        anonymous_demo_user_enabled=_parse_bool(
            os.environ.get("AI_READER_ANONYMOUS_DEMO")
        ),
    )

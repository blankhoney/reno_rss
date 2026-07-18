import pytest

from app.api.routes.ask import MiniMaxAskProvider
from app.core import config


def test_llm_env_parser_golden_table():
    assert config._parse_float(None, 0.2) == 0.2
    assert config._parse_float("", 0.2) == 0.2
    assert config._parse_float(" 0.7 ", 0.2) == 0.7
    with pytest.raises(ValueError):
        config._parse_float("not-a-number", 0.2)

    assert config._parse_bool_with_default(None, True) is True
    assert config._parse_bool_with_default("", False) is False
    assert config._parse_bool_with_default(" YES ", False) is True
    assert config._parse_bool_with_default("off", True) is False
    assert config._parse_bool_with_default("unexpected", True) is False

    assert config._parse_optional_positive_int(None, 16_384) == 16_384
    assert config._parse_optional_positive_int("", 16_384) == 16_384
    assert config._parse_optional_positive_int("4096", 16_384) == 4096
    assert config._parse_optional_positive_int("0", 16_384) is None
    assert config._parse_optional_positive_int("-1", 16_384) is None

    choices = {"adaptive", "disabled"}
    assert config._parse_optional_choice(None, "disabled", choices) == "disabled"
    assert config._parse_optional_choice("", "disabled", choices) is None
    assert config._parse_optional_choice(" ADAPTIVE ", "disabled", choices) == "adaptive"
    with pytest.raises(ValueError, match="adaptive, disabled"):
        config._parse_optional_choice("enabled", "disabled", choices)

    assert config.normalize_database_url(None) is None
    assert config.normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"
    assert (
        config.normalize_database_url("postgres://user:pass@localhost:5432/app")
        == "postgresql+psycopg://user:pass@localhost:5432/app"
    )


def test_minimax_request_json_matches_worker_payload_plus_stream():
    messages = [{"role": "user", "content": "Summarize"}]
    provider = MiniMaxAskProvider(
        api_key="key",
        base_url="https://api.minimax.io/v1",
        model="MiniMax-M2.7",
        temperature=0.2,
        top_p=0.9,
        max_completion_tokens=4096,
        reasoning_split=True,
        thinking_type="disabled",
        timeout_seconds=30,
    )

    assert provider._request_json(messages) == {
        "model": "MiniMax-M2.7",
        "messages": messages,
        "temperature": 0.2,
        "top_p": 0.9,
        "stream": True,
        "max_completion_tokens": 4096,
        "reasoning_split": True,
        "thinking": {"type": "disabled"},
    }

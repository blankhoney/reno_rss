from __future__ import annotations

from fastapi import Request
from slowapi import Limiter

from app.core.config import get_settings


def client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("x-forwarded-for", "")
    if x_forwarded_for:
        peer = x_forwarded_for.split(",")[-1].strip()
        if peer:
            return peer
    return request.client.host if request.client else "anon"


def api_rate_limit(*_args: object, **_kwargs: object) -> str:
    return get_settings().api_ratelimit_default


def llm_rate_limit(*_args: object, **_kwargs: object) -> str:
    return get_settings().llm_ratelimit


def write_rate_limit(*_args: object, **_kwargs: object) -> str:
    return get_settings().write_ratelimit


# In-memory storage is enough for the current single API container. It resets
# on restart and is not shared across future multi-worker deployments.
limiter = Limiter(key_func=client_ip, default_limits=[api_rate_limit])

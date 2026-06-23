import hashlib
import secrets
from urllib.parse import urlparse

from fastapi import Request, Response


SESSION_COOKIE_NAME = "ar_session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_recovery_code() -> str:
    return secrets.token_urlsafe(24)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="Lax",
        path="/",
    )


def has_valid_csrf_origin(request: Request, allowed_origins: set[str]) -> bool:
    if not allowed_origins:
        return True
    origin = request.headers.get("origin")
    if origin is not None:
        return _same_origin(origin, allowed_origins)
    return _same_origin(request.headers.get("referer"), allowed_origins)


def _same_origin(value: str | None, allowed_origins: set[str]) -> bool:
    if value is None:
        return False
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return False
    return f"{parsed.scheme}://{parsed.netloc}" in allowed_origins

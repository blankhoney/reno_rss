from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator

from app.api.deps import ApiError, get_auth_store, require_user
from app.core.security import SESSION_COOKIE_NAME, clear_session_cookie, set_session_cookie
from app.db.auth_store import AuthStore, UserRecord


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def display_name_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name must not be blank")
        return normalized


class RecoverRequest(BaseModel):
    recovery_code: str = Field(min_length=16, max_length=128)


def user_public(user: UserRecord) -> dict[str, object]:
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
) -> dict[str, object]:
    current_token = request.cookies.get(SESSION_COOKIE_NAME)
    user, session_token, recovery_code = store.login(
        display_name=payload.display_name,
        current_session_token=current_token,
    )
    set_session_cookie(response, session_token)
    return {"user": user_public(user), "recovery_code": recovery_code}


@router.post("/recover")
def recover(
    payload: RecoverRequest,
    response: Response,
    store: AuthStore = Depends(get_auth_store),
) -> dict[str, object]:
    recovered = store.recover(payload.recovery_code)
    if recovered is None:
        raise ApiError(400, "invalid_recovery_code", "Invalid recovery code")

    user, session_token, recovery_code = recovered
    set_session_cookie(response, session_token)
    return {"user": user_public(user), "recovery_code": recovery_code}


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    store: AuthStore = Depends(get_auth_store),
) -> Response:
    store.logout(request.cookies.get(SESSION_COOKIE_NAME))
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.get("/me")
def me(current_user: UserRecord = Depends(require_user)) -> dict[str, object]:
    return {"user": user_public(current_user)}

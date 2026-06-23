from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.deps import ApiError, api_error_handler, request_validation_error_handler
from app.api.routes import admin, articles, auth
from app.core.config import APP_VERSION, get_settings
from app.core.security import has_valid_csrf_origin
from app.db.auth_store import create_auth_store


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI Reader API", version=APP_VERSION)
    app.state.auth_store = create_auth_store(settings.database_url)
    app.state.csrf_allowed_origins = settings.csrf_allowed_origins or set()
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)

    @app.middleware("http")
    async def csrf_origin_middleware(request: Request, call_next) -> JSONResponse:
        if request.method in WRITE_METHODS and not has_valid_csrf_origin(
            request,
            request.app.state.csrf_allowed_origins,
        ):
            return await api_error_handler(
                request,
                ApiError(403, "forbidden", "Invalid request origin"),
            )
        return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    @app.get("/api/healthz")
    async def api_healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    app.include_router(auth.router)
    app.include_router(articles.router)
    app.include_router(admin.router)

    return app


app = create_app()

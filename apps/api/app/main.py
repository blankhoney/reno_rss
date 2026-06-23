from datetime import UTC, datetime

from fastapi import FastAPI

from app.core.config import APP_VERSION


def create_app() -> FastAPI:
    app = FastAPI(title="AI Reader API", version=APP_VERSION)

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    @app.get("/api/healthz")
    async def api_healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    return app


app = create_app()

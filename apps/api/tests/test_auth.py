import pytest
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select


pytestmark = pytest.mark.asyncio


async def test_business_route_requires_session(client):
    response = await client.get("/api/articles")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_login_sets_http_only_cookie(client):
    response = await client.post("/api/auth/login", json={"display_name": "Blank"})

    assert response.status_code == 200
    assert "ar_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=Lax" in response.headers["set-cookie"]
    assert response.json()["user"]["display_name"] == "Blank"
    assert response.json()["user"]["role"] == "user"
    assert response.json()["recovery_code"]


async def test_login_validation_uses_error_envelope(client):
    response = await client.post("/api/auth/login", json={"display_name": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unprocessable"
    assert "details" in response.json()["error"]


async def test_login_rejects_whitespace_display_name(client):
    response = await client.post("/api/auth/login", json={"display_name": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unprocessable"


async def test_me_returns_current_user_after_login(client):
    login = await client.post("/api/auth/login", json={"display_name": "Blank"})

    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["id"] == login.json()["user"]["id"]
    assert response.json()["user"]["display_name"] == "Blank"


async def test_user_cannot_access_admin(client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    response = await client.get("/api/admin/users")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_can_access_admin_users(app, client):
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)

    response = await client.get("/api/admin/users")

    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_logout_invalidates_current_session(client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    logout = await client.post("/api/auth/logout")
    response = await client.get("/api/articles")

    assert logout.status_code == 204
    assert "ar_session=" in logout.headers["set-cookie"]
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert response.status_code == 401


async def test_recover_sets_new_session_and_rotates_recovery_code(client):
    login = await client.post("/api/auth/login", json={"display_name": "Blank"})
    recovery_code = login.json()["recovery_code"]
    await client.post("/api/auth/logout")

    recovered = await client.post("/api/auth/recover", json={"recovery_code": recovery_code})

    assert recovered.status_code == 200
    assert recovered.json()["user"]["id"] == login.json()["user"]["id"]
    assert recovered.json()["recovery_code"]
    assert recovered.json()["recovery_code"] != recovery_code
    assert "ar_session=" in recovered.headers["set-cookie"]

    reused = await client.post("/api/auth/recover", json={"recovery_code": recovery_code})
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "invalid_recovery_code"


async def test_write_requests_reject_untrusted_origin(app, client):
    app.state.csrf_allowed_origins = {"https://allowed.test"}

    rejected = await client.post(
        "/api/auth/login",
        json={"display_name": "Blank"},
        headers={"Origin": "https://evil.test"},
    )
    accepted = await client.post(
        "/api/auth/login",
        json={"display_name": "Blank"},
        headers={"Origin": "https://allowed.test"},
    )

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "forbidden"
    assert accepted.status_code == 200


async def test_origin_takes_precedence_over_referer_for_csrf(app, client):
    app.state.csrf_allowed_origins = {"https://allowed.test"}

    response = await client.post(
        "/api/auth/login",
        json={"display_name": "Blank"},
        headers={
            "Origin": "https://evil.test",
            "Referer": "https://allowed.test/account",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_write_requests_allow_referer_when_origin_is_absent(app, client):
    app.state.csrf_allowed_origins = {"https://allowed.test"}

    response = await client.post(
        "/api/auth/login",
        json={"display_name": "Blank"},
        headers={"Referer": "https://allowed.test/account"},
    )

    assert response.status_code == 200


async def test_create_auth_store_uses_database_backend_for_database_url():
    from app.db.auth_store import DatabaseAuthStore, create_auth_store

    store = create_auth_store("postgresql+psycopg://postgres:postgres@localhost/test")

    assert isinstance(store, DatabaseAuthStore)
    store.dispose()


async def test_create_app_normalizes_postgres_database_url(monkeypatch):
    from app.db.auth_store import DatabaseAuthStore
    from app.main import create_app

    monkeypatch.setenv("SCORING_DATABASE_URL", "postgres://postgres:postgres@localhost/test")

    app = create_app()

    assert isinstance(app.state.auth_store, DatabaseAuthStore)
    assert app.state.auth_store.engine.url.drivername == "postgresql+psycopg"
    app.state.auth_store.dispose()


async def test_database_recovery_redeems_code_with_single_conditional_update():
    from app.db.auth_store import DatabaseAuthStore

    class FakeScalarResult:
        def one_or_none(self):
            return None

    class FakeMappingResult:
        def mappings(self):
            return FakeScalarResult()

    class FakeConnection:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)
            return FakeMappingResult()

    class FakeBegin:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, *_args):
            return None

    class FakeEngine:
        def __init__(self):
            self.connection = FakeConnection()

        def begin(self):
            return FakeBegin(self.connection)

    engine = FakeEngine()
    store = DatabaseAuthStore("postgresql+psycopg://postgres:postgres@localhost/test", engine=engine)

    result = store.recover("old-recovery-code")

    assert result is None
    assert not any(isinstance(statement, Select) for statement in engine.connection.statements)
    updates = [
        statement for statement in engine.connection.statements if isinstance(statement, Update)
    ]
    assert len(updates) == 1
    assert "recovery_code_hash" in str(updates[0])

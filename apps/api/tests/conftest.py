import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

for module_name, module in list(sys.modules.items()):
    if module_name != "app" and not module_name.startswith("app."):
        continue
    app_file = getattr(module, "__file__", "")
    if app_file and not str(app_file).startswith(str(API_ROOT)):
        sys.modules.pop(module_name, None)


@pytest.fixture
def app():
    from app.main import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as api_client:
        yield api_client

from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.db.auth_store import UserRecord


router = APIRouter(prefix="/api", tags=["articles"])


@router.get("/articles")
async def list_articles(_current_user: UserRecord = Depends(require_user)) -> dict[str, list[object]]:
    return {"items": []}

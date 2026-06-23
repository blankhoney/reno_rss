from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.db.auth_store import UserRecord


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
async def list_users(_current_user: UserRecord = Depends(require_admin)) -> dict[str, list[object]]:
    return {"items": []}

"""Saved list filters for the current user (name, q, module, sort)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_saved_search_repository, require_user
from app.db.auth_store import UserRecord
from app.db.repositories.articles import LIST_MODULES, LIST_SORTS
from app.db.repositories.saved_searches import SavedSearchRecord, SavedSearchStore


router = APIRouter(prefix="/api/saved-searches", tags=["saved-searches"])

LEGACY_SORT_ALIASES = {
    "published_desc": "latest",
    "published_asc": "latest",
    "score_desc": "score",
    "score_asc": "score",
}


class SavedSearchItem(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    q: str = Field(default="", max_length=200)
    module: str = Field(default="all", max_length=40)
    sort: str = Field(default="latest", max_length=40)

    @field_validator("name", "q")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("module")
    @classmethod
    def validate_module(cls, value: str) -> str:
        module = value.strip() or "all"
        if module not in LIST_MODULES:
            raise ValueError(f"module must be one of: {', '.join(sorted(LIST_MODULES))}")
        return module

    @field_validator("sort")
    @classmethod
    def validate_sort(cls, value: str) -> str:
        return normalize_saved_search_sort(value, strict=True)


class ReplaceSavedSearchesRequest(BaseModel):
    items: list[SavedSearchItem] = Field(default_factory=list, max_length=30)


def saved_search_public(record: SavedSearchRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "name": record.name,
        "q": record.q,
        "module": record.module,
        "sort": normalize_saved_search_sort(record.sort, strict=False),
    }


def normalize_saved_search_sort(value: str, *, strict: bool) -> str:
    sort = value.strip().lower() or "latest"
    sort = LEGACY_SORT_ALIASES.get(sort, sort)
    if sort in LIST_SORTS:
        return sort
    if strict:
        raise ValueError(f"sort must be one of: {', '.join(sorted(LIST_SORTS))}")
    return "latest"


@router.get("")
def list_saved_searches(
    current_user: UserRecord = Depends(require_user),
    repository: SavedSearchStore = Depends(get_saved_search_repository),
) -> dict[str, object]:
    items = repository.list_for_user(current_user.id)
    return {"items": [saved_search_public(item) for item in items]}


@router.put("")
def replace_saved_searches(
    payload: ReplaceSavedSearchesRequest,
    current_user: UserRecord = Depends(require_user),
    repository: SavedSearchStore = Depends(get_saved_search_repository),
) -> dict[str, object]:
    records = repository.replace_for_user(
        current_user.id,
        [
            {
                "name": item.name,
                "q": item.q,
                "module": item.module,
                "sort": item.sort,
            }
            for item in payload.items
        ],
    )
    return {"items": [saved_search_public(item) for item in records]}

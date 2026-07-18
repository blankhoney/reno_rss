"""GET/PUT current user's reader rules."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import ApiError, get_rule_repository, require_user
from app.db.auth_store import UserRecord
from app.db.repositories.rules import RuleStore
from app.domain.rules import Rule, rule_to_public, validate_rule


router = APIRouter(prefix="/api/rules", tags=["rules"])


class RulePayload(BaseModel):
    type: str
    feed_id: int | None = None
    keyword: str | None = None
    weight: float | None = None


class RulesPutRequest(BaseModel):
    rules: list[RulePayload] = Field(default_factory=list, max_length=100)


def _parse_rules(payloads: list[RulePayload]) -> list[Rule]:
    try:
        return [validate_rule(item.model_dump()) for item in payloads]
    except ValueError as exc:
        raise ApiError(400, "invalid_rule", str(exc)) from exc


@router.get("")
def get_rules(
    current_user: UserRecord = Depends(require_user),
    rule_repository: RuleStore = Depends(get_rule_repository),
) -> dict[str, object]:
    rules = rule_repository.get_rules(current_user.id)
    return {"rules": [rule_to_public(rule) for rule in rules]}


@router.put("")
def put_rules(
    body: RulesPutRequest,
    current_user: UserRecord = Depends(require_user),
    rule_repository: RuleStore = Depends(get_rule_repository),
) -> dict[str, object]:
    rules = _parse_rules(body.rules)
    stored = rule_repository.put_rules(current_user.id, rules)
    return {"rules": [rule_to_public(rule) for rule in stored]}

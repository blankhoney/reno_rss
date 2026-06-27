from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, select, update

from app.db.models import article_base_scores, scoring_batch_items, scoring_batches


@dataclass(frozen=True)
class ScoreRecord:
    id: int
    article_id: int
    batch_id: int | None
    base_score: int
    recommendation_tier: str
    summary_zh: str
    summary_original: str
    source_language: str
    dimension_scores: dict[str, object]
    dimension_reasons: dict[str, object]
    tags: list[object]
    reason: str
    risk_flags: list[object]
    confidence: float
    rubric_version: str
    model_provider: str
    model_name: str
    prompt_version: str
    scoring_status: str
    error: str | None
    is_active: bool
    scored_at: datetime


@dataclass(frozen=True)
class ScoringBatchItemRecord:
    id: int
    batch_id: int
    article_id: int
    status: str
    base_score_id: int | None
    error: str | None


@dataclass(frozen=True)
class ScoringBatchRecord:
    id: int
    name: str | None
    status: str
    trigger_type: str
    candidate_window: str
    article_count: int
    created_by: UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    items: list[ScoringBatchItemRecord]


class ScoringStore(Protocol):
    def create_score(
        self,
        *,
        article_id: int,
        base_score: int,
        is_active: bool,
        batch_id: int | None = None,
    ) -> ScoreRecord: ...

    def list_scores(self, *, article_id: int) -> list[ScoreRecord]: ...

    def active_scores_for_articles(
        self, article_ids: list[int]
    ) -> dict[int, ScoreRecord]: ...

    def create_batch(
        self,
        *,
        name: str | None,
        candidate_window: str,
        article_ids: list[int],
        created_by: UUID | None,
    ) -> ScoringBatchRecord: ...

    def get_batch(self, batch_id: int) -> ScoringBatchRecord | None: ...


class MemoryScoringRepository:
    def __init__(self) -> None:
        self._scores: dict[int, ScoreRecord] = {}
        self._batches: dict[int, ScoringBatchRecord] = {}
        self._next_score_id = 1
        self._next_batch_id = 1
        self._next_batch_item_id = 1

    def create_score(
        self,
        *,
        article_id: int,
        base_score: int,
        is_active: bool,
        batch_id: int | None = None,
    ) -> ScoreRecord:
        if is_active:
            for score_id, score in list(self._scores.items()):
                if score.article_id == article_id and score.is_active:
                    self._scores[score_id] = replace(score, is_active=False)

        now = datetime.now(UTC)
        score = ScoreRecord(
            id=self._next_score_id,
            article_id=article_id,
            batch_id=batch_id,
            base_score=base_score,
            recommendation_tier=tier_for_score(base_score),
            summary_zh="",
            summary_original="",
            source_language="unknown",
            dimension_scores={},
            dimension_reasons={},
            tags=[],
            reason="",
            risk_flags=[],
            confidence=1,
            rubric_version="v1",
            model_provider="mock",
            model_name="mock",
            prompt_version="rss-score-v05",
            scoring_status="success",
            error=None,
            is_active=is_active,
            scored_at=now,
        )
        self._scores[score.id] = score
        self._next_score_id += 1
        return score

    def list_scores(self, *, article_id: int) -> list[ScoreRecord]:
        return [
            score for score in sorted(self._scores.values(), key=lambda item: item.id)
            if score.article_id == article_id
        ]

    def active_scores_for_articles(
        self, article_ids: list[int]
    ) -> dict[int, ScoreRecord]:
        wanted = set(article_ids)
        result: dict[int, ScoreRecord] = {}
        for score in sorted(self._scores.values(), key=lambda item: item.id):
            if score.is_active and score.article_id in wanted:
                result[score.article_id] = score
        return result

    def create_batch(
        self,
        *,
        name: str | None,
        candidate_window: str,
        article_ids: list[int],
        created_by: UUID | None,
    ) -> ScoringBatchRecord:
        batch_id = self._next_batch_id
        self._next_batch_id += 1
        items = []
        for article_id in article_ids:
            items.append(
                ScoringBatchItemRecord(
                    id=self._next_batch_item_id,
                    batch_id=batch_id,
                    article_id=article_id,
                    status="pending",
                    base_score_id=None,
                    error=None,
                )
            )
            self._next_batch_item_id += 1

        batch = ScoringBatchRecord(
            id=batch_id,
            name=name,
            status="queued",
            trigger_type="manual",
            candidate_window=candidate_window,
            article_count=len(items),
            created_by=created_by,
            created_at=datetime.now(UTC),
            started_at=None,
            finished_at=None,
            items=items,
        )
        self._batches[batch.id] = batch
        return batch

    def get_batch(self, batch_id: int) -> ScoringBatchRecord | None:
        return self._batches.get(batch_id)


class DatabaseScoringRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def create_score(
        self,
        *,
        article_id: int,
        base_score: int,
        is_active: bool,
        batch_id: int | None = None,
    ) -> ScoreRecord:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            if is_active:
                connection.execute(
                    update(article_base_scores)
                    .where(
                        article_base_scores.c.article_id == article_id,
                        article_base_scores.c.is_active.is_(True),
                    )
                    .values(is_active=False)
                )
            row = (
                connection.execute(
                    article_base_scores.insert()
                    .values(
                        article_id=article_id,
                        batch_id=batch_id,
                        base_score=base_score,
                        recommendation_tier=tier_for_score(base_score),
                        summary_zh="",
                        summary_original="",
                        source_language="unknown",
                        dimension_scores={},
                        dimension_reasons={},
                        tags=[],
                        reason="",
                        risk_flags=[],
                        confidence=1,
                        rubric_version="v1",
                        model_provider="mock",
                        model_name="mock",
                        prompt_version="rss-score-v05",
                        scoring_status="success",
                        is_active=is_active,
                        scored_at=now,
                    )
                    .returning(article_base_scores)
                )
                .mappings()
                .one()
            )
        return _score_from_row(row)

    def list_scores(self, *, article_id: int) -> list[ScoreRecord]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(article_base_scores)
                    .where(article_base_scores.c.article_id == article_id)
                    .order_by(article_base_scores.c.id.asc())
                )
                .mappings()
                .all()
            )
        return [_score_from_row(row) for row in rows]

    def active_scores_for_articles(
        self, article_ids: list[int]
    ) -> dict[int, ScoreRecord]:
        if not article_ids:
            return {}
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(article_base_scores).where(
                        article_base_scores.c.article_id.in_(article_ids),
                        article_base_scores.c.is_active.is_(True),
                    )
                )
                .mappings()
                .all()
            )
        return {row["article_id"]: _score_from_row(row) for row in rows}

    def create_batch(
        self,
        *,
        name: str | None,
        candidate_window: str,
        article_ids: list[int],
        created_by: UUID | None,
    ) -> ScoringBatchRecord:
        with self.engine.begin() as connection:
            batch_row = (
                connection.execute(
                    scoring_batches.insert()
                    .values(
                        name=name,
                        status="queued",
                        trigger_type="manual",
                        candidate_window=candidate_window,
                        article_count=len(article_ids),
                        created_by=created_by,
                    )
                    .returning(scoring_batches)
                )
                .mappings()
                .one()
            )
            item_rows = []
            for article_id in article_ids:
                item_rows.append(
                    connection.execute(
                        scoring_batch_items.insert()
                        .values(batch_id=batch_row["id"], article_id=article_id, status="pending")
                        .returning(scoring_batch_items)
                    )
                    .mappings()
                    .one()
                )
        return _batch_from_rows(batch_row, item_rows)

    def get_batch(self, batch_id: int) -> ScoringBatchRecord | None:
        with self.engine.begin() as connection:
            batch_row = (
                connection.execute(select(scoring_batches).where(scoring_batches.c.id == batch_id))
                .mappings()
                .one_or_none()
            )
            if batch_row is None:
                return None
            item_rows = (
                connection.execute(
                    select(scoring_batch_items)
                    .where(scoring_batch_items.c.batch_id == batch_id)
                    .order_by(scoring_batch_items.c.id.asc())
                )
                .mappings()
                .all()
            )
        return _batch_from_rows(batch_row, item_rows)

    def dispose(self) -> None:
        self.engine.dispose()


def create_scoring_repository(database_url: str | None) -> ScoringStore:
    if database_url:
        return DatabaseScoringRepository(database_url)
    return MemoryScoringRepository()


def tier_for_score(score: int) -> str:
    if score >= 85:
        return "must_read"
    if score >= 70:
        return "read"
    if score >= 50:
        return "skim"
    return "skip"


def _score_from_row(row) -> ScoreRecord:
    confidence = row["confidence"]
    return ScoreRecord(
        id=row["id"],
        article_id=row["article_id"],
        batch_id=row["batch_id"],
        base_score=row["base_score"],
        recommendation_tier=row["recommendation_tier"],
        summary_zh=row["summary_zh"],
        summary_original=row["summary_original"],
        source_language=row["source_language"],
        dimension_scores=row["dimension_scores"],
        dimension_reasons=row["dimension_reasons"],
        tags=row["tags"],
        reason=row["reason"],
        risk_flags=row["risk_flags"],
        confidence=float(confidence) if isinstance(confidence, Decimal) else confidence,
        rubric_version=row["rubric_version"],
        model_provider=row["model_provider"],
        model_name=row["model_name"],
        prompt_version=row["prompt_version"],
        scoring_status=row["scoring_status"],
        error=row["error"],
        is_active=bool(row["is_active"]),
        scored_at=row["scored_at"],
    )


def _batch_item_from_row(row) -> ScoringBatchItemRecord:
    return ScoringBatchItemRecord(
        id=row["id"],
        batch_id=row["batch_id"],
        article_id=row["article_id"],
        status=row["status"],
        base_score_id=row["base_score_id"],
        error=row["error"],
    )


def _batch_from_rows(batch_row, item_rows) -> ScoringBatchRecord:
    return ScoringBatchRecord(
        id=batch_row["id"],
        name=batch_row["name"],
        status=batch_row["status"],
        trigger_type=batch_row["trigger_type"],
        candidate_window=batch_row["candidate_window"],
        article_count=batch_row["article_count"],
        created_by=batch_row["created_by"],
        created_at=batch_row["created_at"],
        started_at=batch_row["started_at"],
        finished_at=batch_row["finished_at"],
        items=[_batch_item_from_row(row) for row in item_rows],
    )

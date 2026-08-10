from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from functools import wraps
from threading import RLock
import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Protocol
from uuid import UUID
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import Engine, Numeric, and_, bindparam, case, create_engine, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.domain.annotations_meta import searchable_annotation_body
from app.db.models import (
    article_annotations,
    article_base_scores,
    article_sources,
    articles,
    categories,
    feeds,
    user_article_feedback_scores,
    user_article_states,
    user_feed_subscriptions,
)

# State/queue modules filtered server-side. Dimension modules map to "all"
# for SQL (ranking still uses client score formulas until composite cursors).
LIST_STATE_MODULES = frozenset({"all", "unread", "read", "starred", "project", "read-later"})
LIST_DIMENSION_MODULES = frozenset(
    {"technical", "business", "trend", "ai", "product", "security"}
)
LIST_MODULES = LIST_STATE_MODULES | LIST_DIMENSION_MODULES
LIST_SORTS = frozenset({"default", "latest", "score", "technical", "business", "trend"})


def normalize_list_module(module: str | None) -> str:
    if module is None or module == "":
        return "all"
    if module not in LIST_MODULES:
        raise ValueError(f"unsupported list module: {module}")
    if module in LIST_DIMENSION_MODULES:
        return "all"
    return module


TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


@dataclass(frozen=True)
class ArticleRecord:
    id: int
    primary_feed_id: int | None
    title: str
    url: str
    canonical_url: str | None
    author: str | None
    published_at: datetime | None
    content_text: str | None
    content_html: str | None
    content_zh: str | None
    content_zh_status: str | None
    translated_at: datetime | None
    content_source: str | None
    content_quality: str | None
    content_hash: str | None
    dedup_key: str | None
    fetched_at: datetime | None
    content_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    feed_title: str | None = None
    category_id: int | None = None
    category_title: str | None = None
    source_count: int = 0


@dataclass(frozen=True)
class ArticleSourceRecord:
    article_id: int
    feed_id: int
    feed_title: str | None
    miniflux_entry_id: int
    source_url: str | None
    source_title: str | None
    published_at: datetime | None


@dataclass(frozen=True)
class ArticleStateRecord:
    status: str
    saved: bool
    project: bool
    read_progress: float
    updated_at: datetime | None = None


def state_matches_module(state: ArticleStateRecord, module: str) -> bool:
    if module == "all":
        return True
    if module == "unread":
        return state.status == "unread"
    if module == "read":
        return state.status == "read"
    if module == "starred":
        return state.saved is True
    if module == "read-later":
        return state.status == "unread" and 0 < state.read_progress < 1
    if module == "project":
        return state.project is True
    return True


@dataclass(frozen=True)
class ArticleFeedbackRecord:
    user_score: int
    feedback_type: str
    reason: str
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class ArticlePage:
    items: list[ArticleRecord]
    next_cursor: str | None
    has_more: bool


class AnnotationDeleteResult(StrEnum):
    DELETED = "deleted"
    ALREADY_DELETED = "already_deleted"
    NOT_FOUND_OR_NOT_OWNER = "not_found_or_not_owner"


@dataclass(frozen=True)
class AnnotationRecord:
    id: int
    article_id: int
    user_id: UUID
    type: str
    selected_text: str | None
    content: str
    created_at: datetime
    updated_at: datetime
    next_review_at: datetime | None = None
    interval_days: int = 1
    review_count: int = 0
    deleted_at: datetime | None = None
    deleted_by: UUID | None = None
    delete_reason: str | None = None


class ArticleStore(Protocol):
    def upsert_from_source(self, entry: dict[str, object]) -> ArticleRecord: ...

    def sources_for_article(self, article_id: int) -> list[ArticleSourceRecord]: ...

    def list_articles(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        user_id: UUID | None = None,
        module: str = "all",
        q: str | None = None,
        sort: str | None = None,
        score_lookup: Callable[[list[int]], Mapping[int, object]] | None = None,
    ) -> ArticlePage: ...

    def count_articles(self) -> int: ...

    def get_article(self, article_id: int) -> ArticleRecord | None: ...

    def get_articles(self, article_ids: list[int]) -> dict[int, ArticleRecord]: ...

    def get_state(self, user_id: UUID, article_id: int) -> ArticleStateRecord: ...

    def get_states(self, user_id: UUID, article_ids: list[int]) -> dict[int, ArticleStateRecord]: ...

    def upsert_state(
        self,
        user_id: UUID,
        article_id: int,
        *,
        status: str | None = None,
        saved: bool | None = None,
        project: bool | None = None,
        read_progress: float | None = None,
    ) -> ArticleStateRecord | None: ...

    def list_annotations(self, user_id: UUID, article_id: int) -> list[AnnotationRecord]: ...

    def list_annotations_for_articles(
        self,
        user_id: UUID,
        article_ids: list[int],
    ) -> dict[int, list[AnnotationRecord]]: ...

    def list_recent_annotations(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
    ) -> list[AnnotationRecord]: ...

    def list_due_annotations(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[AnnotationRecord]: ...

    def search_annotations(
        self,
        user_id: UUID,
        *,
        q: str,
        limit: int = 30,
    ) -> list[AnnotationRecord]: ...

    def get_annotation(self, user_id: UUID, annotation_id: int) -> AnnotationRecord | None: ...

    def update_annotation(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        content: str,
    ) -> AnnotationRecord | None: ...

    def soft_delete_annotation(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        delete_reason: str = "user_request",
    ) -> AnnotationDeleteResult: ...

    def update_annotation_review(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        next_review_at: datetime,
        interval_days: int,
        review_count: int,
    ) -> AnnotationRecord | None: ...

    def create_annotation(
        self,
        user_id: UUID,
        article_id: int,
        *,
        content: str,
        selected_text: str | None = None,
        annotation_type: str = "annotation",
    ) -> AnnotationRecord | None: ...

    def get_feedback(self, user_id: UUID, article_id: int) -> ArticleFeedbackRecord | None: ...

    def get_feedbacks(
        self,
        user_id: UUID,
        article_ids: list[int],
    ) -> dict[int, ArticleFeedbackRecord]: ...

    def feed_governance_for_user(
        self,
        user_id: UUID,
        feed_ids: list[int],
    ) -> dict[int, dict[str, object]]: ...

    def upsert_feedback(
        self,
        user_id: UUID,
        article_id: int,
        *,
        user_score: int,
        feedback_type: str,
        reason: str,
    ) -> ArticleFeedbackRecord | None: ...

    def save_translation(
        self,
        article_id: int,
        *,
        content_zh: str | None,
        status: str | None,
        translated_at: datetime | None,
    ) -> ArticleRecord | None: ...


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            query,
            "",
        )
    )


def dedup_key_for_entry(url: str, title: str, content_text: str | None = None) -> str:
    canonical_url = canonicalize_url(url)
    if canonical_url:
        return canonical_url
    content_hash = _content_hash(content_text)
    return hashlib.sha256(f"{title.strip().lower()}:{content_hash}".encode("utf-8")).hexdigest()


def encode_article_cursor(article: ArticleRecord) -> str:
    payload = {
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "id": article.id,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def decode_article_cursor(cursor: str) -> tuple[datetime | None, int]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    published_at = payload.get("published_at")
    return (
        datetime.fromisoformat(published_at) if published_at is not None else None,
        int(payload["id"]),
    )


def resolve_rank_sort(sort: str | None, module: str | None) -> str | None:
    """Resolve explicit sort or a dimension module's default ranking."""
    requested = (sort or "default").strip().lower()
    if requested not in LIST_SORTS:
        raise ValueError(f"unsupported list sort: {requested}")
    if requested in {"default", "latest"}:
        return f"module:{module}" if module in LIST_DIMENSION_MODULES else None
    return requested


def encode_ranked_article_cursor(sort_key: str, rank: float, article_id: int) -> str:
    payload = {"sort": sort_key, "rank": rank, "id": article_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def decode_ranked_article_cursor(cursor: str, *, sort_key: str) -> tuple[float, int]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    if payload.get("sort") != sort_key:
        raise ValueError("cursor sort does not match request")
    return float(payload["rank"]), int(payload["id"])


def article_rank_value(score: object | None, sort_key: str) -> float:
    if score is None:
        return -1.0
    base_score = float(getattr(score, "base_score", -1) or 0)
    dimensions = getattr(score, "dimension_scores", {})
    dims = dimensions if isinstance(dimensions, Mapping) else {}

    def dimension(name: str) -> float:
        value = dims.get(name)
        return float(value) if value is not None else 0.0

    if sort_key == "score":
        return base_score
    if sort_key == "technical":
        return dimension("topic_relevance")
    if sort_key == "business":
        return dimension("actionability")
    if sort_key == "trend":
        return dimension("novelty")
    if sort_key in {"module:technical", "module:ai"}:
        return (dimension("topic_relevance") + dimension("information_density")) / 2
    if sort_key == "module:business":
        return dimension("actionability")
    if sort_key == "module:trend":
        return (dimension("novelty") + dimension("timeliness")) / 2
    if sort_key == "module:product":
        return (dimension("actionability") + dimension("reading_cost_fit")) / 2
    if sort_key == "module:security":
        return (dimension("source_quality") + (100 - dimension("risk_uncertainty"))) / 2
    raise ValueError(f"unsupported rank sort: {sort_key}")


def _with_memory_article_lock(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return locked


class MemoryArticleRepository:
    def __init__(self, lock: RLock | None = None) -> None:
        self._lock = lock or RLock()
        self._articles: dict[int, ArticleRecord] = {}
        self._article_ids_by_dedup_key: dict[str, int] = {}
        self._feed_titles: dict[int, str | None] = {}
        self._feed_categories: dict[int, tuple[int | None, str | None]] = {}
        self._sources_by_feed_entry: dict[tuple[int, int], ArticleSourceRecord] = {}
        self._states: dict[tuple[UUID, int], ArticleStateRecord] = {}
        self._feedbacks: dict[tuple[UUID, int], ArticleFeedbackRecord] = {}
        self._annotations: dict[int, AnnotationRecord] = {}
        # user_id -> feed_id -> {hidden, quality_score, user_priority}
        self._feed_governance: dict[tuple[UUID, int], dict[str, object]] = {}
        self._next_id = 1
        self._next_annotation_id = 1

    @_with_memory_article_lock
    def upsert_from_source(self, entry: dict[str, object]) -> ArticleRecord:
        feed_id = int(entry["feed_id"])
        miniflux_entry_id = int(entry["miniflux_entry_id"])
        url = str(entry["url"])
        title = str(entry["title"])
        feed_title = _optional_str(entry.get("feed_title"))
        category_id = _optional_int(entry.get("category_id"))
        category_title = _optional_str(entry.get("category_title"))
        self._feed_titles[feed_id] = feed_title
        self._feed_categories[feed_id] = (category_id, category_title)
        content_text = _optional_str(entry.get("content_text"))
        dedup_key = dedup_key_for_entry(url, title, content_text)
        article_id = self._article_ids_by_dedup_key.get(dedup_key)
        now = datetime.now(UTC)

        if article_id is None:
            article_id = self._next_id
            self._next_id += 1
            article = ArticleRecord(
                id=article_id,
                primary_feed_id=feed_id,
                title=title,
                url=url,
                canonical_url=canonicalize_url(url),
                author=_optional_str(entry.get("author")),
                published_at=_optional_datetime(entry.get("published_at")),
                content_text=content_text,
                content_html=_optional_str(entry.get("content_html")),
                content_zh=None,
                content_zh_status=None,
                translated_at=None,
                content_source=_optional_str(entry.get("content_source")),
                content_quality=_optional_str(entry.get("content_quality")),
                content_hash=_content_hash(content_text),
                dedup_key=dedup_key,
                fetched_at=_optional_datetime(entry.get("fetched_at")),
                content_expires_at=_optional_datetime(entry.get("content_expires_at")),
                created_at=now,
                updated_at=now,
            )
            self._articles[article_id] = article
            self._article_ids_by_dedup_key[dedup_key] = article_id
        else:
            article = self._articles[article_id]

        source = ArticleSourceRecord(
            article_id=article_id,
            feed_id=feed_id,
            feed_title=feed_title,
            miniflux_entry_id=miniflux_entry_id,
            source_url=url,
            source_title=title,
            published_at=_optional_datetime(entry.get("published_at")),
        )
        self._sources_by_feed_entry[(feed_id, miniflux_entry_id)] = source
        article = self._with_source_metadata(article)
        self._articles[article_id] = article
        return article

    def sources_for_article(self, article_id: int) -> list[ArticleSourceRecord]:
        return sorted(
            [
                replace(source, feed_title=self._feed_titles.get(source.feed_id))
                for source in self._sources_by_feed_entry.values()
                if source.article_id == article_id
            ],
            key=lambda source: (source.feed_id, source.miniflux_entry_id),
        )

    @_with_memory_article_lock
    def list_articles(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        user_id: UUID | None = None,
        module: str = "all",
        q: str | None = None,
        sort: str | None = None,
        score_lookup: Callable[[list[int]], Mapping[int, object]] | None = None,
    ) -> ArticlePage:
        list_module = normalize_list_module(module)
        rank_sort = resolve_rank_sort(sort, module)
        query = (q or "").strip().lower()
        items = sorted(
            [self._with_source_metadata(article) for article in self._articles.values()],
            key=lambda article: (
                article.published_at or datetime.min.replace(tzinfo=UTC),
                article.id,
            ),
            reverse=True,
        )
        if query:
            items = [
                article
                for article in items
                if _article_matches_query(article, query)
            ]
        if list_module != "all":
            if user_id is None:
                raise ValueError("user_id is required for non-all list modules")
            items = [
                article
                for article in items
                if state_matches_module(self.get_state(user_id, article.id), list_module)
            ]
        scores: Mapping[int, object] = {}
        if rank_sort is not None:
            if score_lookup is None:
                raise ValueError("score_lookup is required for ranked article lists")
            scores = score_lookup([article.id for article in items])
            items.sort(
                key=lambda article: (
                    article_rank_value(scores.get(article.id), rank_sort),
                    article.id,
                ),
                reverse=True,
            )
        if cursor and rank_sort is not None:
            cursor_rank, cursor_id = decode_ranked_article_cursor(
                cursor,
                sort_key=rank_sort,
            )
            items = [
                article
                for article in items
                if (
                    article_rank_value(scores.get(article.id), rank_sort),
                    article.id,
                )
                < (cursor_rank, cursor_id)
            ]
        elif cursor:
            cursor_published_at, cursor_id = decode_article_cursor(cursor)
            items = [
                article
                for article in items
                if _is_after_cursor(article, cursor_published_at, cursor_id)
            ]

        page_items = items[:limit]
        has_more = len(items) > limit
        if has_more and page_items and rank_sort is not None:
            last = page_items[-1]
            next_cursor = encode_ranked_article_cursor(
                rank_sort,
                article_rank_value(scores.get(last.id), rank_sort),
                last.id,
            )
        else:
            next_cursor = encode_article_cursor(page_items[-1]) if has_more and page_items else None
        return ArticlePage(items=page_items, next_cursor=next_cursor, has_more=has_more)

    @_with_memory_article_lock
    def count_articles(self) -> int:
        return len(self._articles)

    @_with_memory_article_lock
    def get_article(self, article_id: int) -> ArticleRecord | None:
        article = self._articles.get(article_id)
        return self._with_source_metadata(article) if article is not None else None

    @_with_memory_article_lock
    def get_articles(self, article_ids: list[int]) -> dict[int, ArticleRecord]:
        unique_article_ids = _unique_article_ids(article_ids)
        return {
            article_id: article
            for article_id in unique_article_ids
            if (article := self.get_article(article_id)) is not None
        }

    def get_state(self, user_id: UUID, article_id: int) -> ArticleStateRecord:
        return self._states.get((user_id, article_id), _default_state())

    def get_states(self, user_id: UUID, article_ids: list[int]) -> dict[int, ArticleStateRecord]:
        return {article_id: self.get_state(user_id, article_id) for article_id in article_ids}

    def upsert_state(
        self,
        user_id: UUID,
        article_id: int,
        *,
        status: str | None = None,
        saved: bool | None = None,
        project: bool | None = None,
        read_progress: float | None = None,
    ) -> ArticleStateRecord | None:
        if article_id not in self._articles:
            return None
        current = self.get_state(user_id, article_id)
        next_saved = saved if saved is not None else current.saved
        next_project = False if next_saved is False else project if project is not None else current.project
        updated = replace(
            current,
            status=status if status is not None else current.status,
            saved=next_saved,
            project=next_project,
            read_progress=read_progress if read_progress is not None else current.read_progress,
            updated_at=datetime.now(UTC),
        )
        self._states[(user_id, article_id)] = updated
        return updated

    def list_annotations(self, user_id: UUID, article_id: int) -> list[AnnotationRecord]:
        return sorted(
            [
                annotation
                for annotation in self._annotations.values()
                if (
                    annotation.user_id == user_id
                    and annotation.article_id == article_id
                    and annotation.deleted_at is None
                )
            ],
            key=lambda item: item.id,
            reverse=True,
        )

    def list_annotations_for_articles(
        self,
        user_id: UUID,
        article_ids: list[int],
    ) -> dict[int, list[AnnotationRecord]]:
        wanted = set(article_ids)
        grouped: dict[int, list[AnnotationRecord]] = defaultdict(list)
        for annotation in self._annotations.values():
            if (
                annotation.user_id == user_id
                and annotation.article_id in wanted
                and annotation.deleted_at is None
            ):
                grouped[annotation.article_id].append(annotation)
        return {
            article_id: sorted(items, key=lambda item: item.id, reverse=True)
            for article_id, items in grouped.items()
        }

    def list_recent_annotations(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
    ) -> list[AnnotationRecord]:
        items = sorted(
            [
                annotation
                for annotation in self._annotations.values()
                if annotation.user_id == user_id and annotation.deleted_at is None
            ],
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        return items[: max(1, min(limit, 100))]

    def list_due_annotations(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[AnnotationRecord]:
        from app.domain.spaced_review import is_due

        moment = now or datetime.now(UTC)
        items = [
            annotation
            for annotation in self._annotations.values()
            if annotation.user_id == user_id
            and annotation.deleted_at is None
            and is_due(
                annotation.next_review_at,
                now=moment,
                created_at=annotation.created_at,
            )
        ]
        items.sort(
            key=lambda item: (
                item.next_review_at or item.created_at,
                item.id,
            )
        )
        return items[: max(1, min(limit, 100))]

    def search_annotations(
        self,
        user_id: UUID,
        *,
        q: str,
        limit: int = 30,
    ) -> list[AnnotationRecord]:
        needle = (q or "").strip().casefold()
        if not needle:
            return []
        capped = max(1, min(limit, 100))
        items: list[AnnotationRecord] = []
        for annotation in self._annotations.values():
            if annotation.user_id != user_id or annotation.deleted_at is not None:
                continue
            body = searchable_annotation_body(annotation.content)
            if needle in body.casefold() or needle in (annotation.selected_text or "").casefold():
                items.append(annotation)
        items.sort(key=lambda item: item.id, reverse=True)
        return items[:capped]

    def get_annotation(self, user_id: UUID, annotation_id: int) -> AnnotationRecord | None:
        record = self._annotations.get(annotation_id)
        if record is None or record.user_id != user_id or record.deleted_at is not None:
            return None
        return record

    def update_annotation(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        content: str,
    ) -> AnnotationRecord | None:
        current = self.get_annotation(user_id, annotation_id)
        if current is None:
            return None
        updated = replace(
            current,
            content=content,
            updated_at=datetime.now(UTC),
        )
        self._annotations[annotation_id] = updated
        return updated

    @_with_memory_article_lock
    def soft_delete_annotation(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        delete_reason: str = "user_request",
    ) -> AnnotationDeleteResult:
        current = self._annotations.get(annotation_id)
        if current is None or current.user_id != user_id:
            return AnnotationDeleteResult.NOT_FOUND_OR_NOT_OWNER
        if current.deleted_at is not None:
            return AnnotationDeleteResult.ALREADY_DELETED
        now = datetime.now(UTC)
        self._annotations[annotation_id] = replace(
            current,
            deleted_at=now,
            deleted_by=user_id,
            delete_reason=delete_reason,
            updated_at=now,
        )
        return AnnotationDeleteResult.DELETED

    def update_annotation_review(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        next_review_at: datetime,
        interval_days: int,
        review_count: int,
    ) -> AnnotationRecord | None:
        current = self.get_annotation(user_id, annotation_id)
        if current is None:
            return None
        updated = replace(
            current,
            next_review_at=next_review_at,
            interval_days=interval_days,
            review_count=review_count,
            updated_at=datetime.now(UTC),
        )
        self._annotations[annotation_id] = updated
        return updated

    def create_annotation(
        self,
        user_id: UUID,
        article_id: int,
        *,
        content: str,
        selected_text: str | None = None,
        annotation_type: str = "annotation",
    ) -> AnnotationRecord | None:
        from app.domain.spaced_review import initial_review_schedule

        if article_id not in self._articles:
            return None
        if annotation_type not in {"annotation", "comment", "review"}:
            raise ValueError("unsupported annotation type")
        now = datetime.now(UTC)
        schedule = initial_review_schedule(now)
        record = AnnotationRecord(
            id=self._next_annotation_id,
            article_id=article_id,
            user_id=user_id,
            type=annotation_type,
            selected_text=selected_text,
            content=content,
            created_at=now,
            updated_at=now,
            next_review_at=schedule.next_review_at,
            interval_days=schedule.interval_days,
            review_count=schedule.review_count,
        )
        self._annotations[record.id] = record
        self._next_annotation_id += 1
        return record

    def get_feedback(self, user_id: UUID, article_id: int) -> ArticleFeedbackRecord | None:
        return self._feedbacks.get((user_id, article_id))

    def get_feedbacks(
        self,
        user_id: UUID,
        article_ids: list[int],
    ) -> dict[int, ArticleFeedbackRecord]:
        article_id_set = set(article_ids)
        return {
            article_id: feedback
            for (feedback_user_id, article_id), feedback in self._feedbacks.items()
            if feedback_user_id == user_id and article_id in article_id_set
        }

    def feed_governance_for_user(
        self,
        user_id: UUID,
        feed_ids: list[int],
    ) -> dict[int, dict[str, object]]:
        result: dict[int, dict[str, object]] = {}
        for feed_id in feed_ids:
            meta = self._feed_governance.get((user_id, int(feed_id)))
            if meta is None:
                result[int(feed_id)] = {"hidden": False, "quality_score": 70.0}
            else:
                result[int(feed_id)] = dict(meta)
        return result

    def set_feed_governance_for_tests(
        self,
        user_id: UUID,
        feed_id: int,
        *,
        hidden: bool = False,
        quality_score: float = 70.0,
    ) -> None:
        self._feed_governance[(user_id, int(feed_id))] = {
            "hidden": hidden,
            "quality_score": quality_score,
        }

    def upsert_feedback(
        self,
        user_id: UUID,
        article_id: int,
        *,
        user_score: int,
        feedback_type: str,
        reason: str,
    ) -> ArticleFeedbackRecord | None:
        if article_id not in self._articles:
            return None
        now = datetime.now(UTC)
        current = self.get_feedback(user_id, article_id)
        feedback = ArticleFeedbackRecord(
            user_score=user_score,
            feedback_type=feedback_type,
            reason=reason,
            created_at=current.created_at if current is not None else now,
            updated_at=now,
        )
        self._feedbacks[(user_id, article_id)] = feedback
        return feedback

    @_with_memory_article_lock
    def save_translation(
        self,
        article_id: int,
        *,
        content_zh: str | None,
        status: str | None,
        translated_at: datetime | None,
    ) -> ArticleRecord | None:
        article = self._articles.get(article_id)
        if article is None:
            return None
        updated = replace(
            article,
            content_zh=content_zh,
            content_zh_status=status,
            translated_at=translated_at,
            updated_at=datetime.now(UTC),
        )
        self._articles[article_id] = updated
        return updated

    def _snapshot_translation_locked(self, article_id: int) -> ArticleRecord | None:
        return self._articles.get(article_id)

    def _restore_translation_locked(
        self,
        article_id: int,
        snapshot: ArticleRecord | None,
    ) -> None:
        if snapshot is None:
            self._articles.pop(article_id, None)
        else:
            self._articles[article_id] = snapshot

    def _with_source_metadata(self, article: ArticleRecord) -> ArticleRecord:
        source_count = sum(
            1 for source in self._sources_by_feed_entry.values() if source.article_id == article.id
        )
        category_id = None
        category_title = None
        if article.primary_feed_id is not None:
            category_id, category_title = self._feed_categories.get(
                article.primary_feed_id,
                (None, None),
            )
        return replace(
            article,
            feed_title=self._feed_titles.get(article.primary_feed_id),
            category_id=category_id,
            category_title=category_title,
            source_count=source_count,
        )


class DatabaseArticleRepository:
    def __init__(
        self,
        database_url: str,
        engine: Engine | None = None,
        *,
        annotation_delete_transaction_observer: Callable[[Connection], None] | None = None,
    ) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)
        self._annotation_delete_transaction_observer = annotation_delete_transaction_observer

    def upsert_from_source(self, entry: dict[str, object]) -> ArticleRecord:
        feed_id = int(entry["feed_id"])
        miniflux_entry_id = int(entry["miniflux_entry_id"])
        url = str(entry["url"])
        title = str(entry["title"])
        content_text = _optional_str(entry.get("content_text"))
        dedup_key = dedup_key_for_entry(url, title, content_text)

        with self.engine.begin() as connection:
            row = connection.execute(
                select(articles).where(articles.c.dedup_key == dedup_key)
            ).mappings().one_or_none()
            if row is None:
                row = self._insert_article(connection, entry, dedup_key)

            article = _article_from_row(row)
            self._upsert_source(
                connection,
                article.id,
                feed_id,
                miniflux_entry_id,
                url,
                title,
                _optional_datetime(entry.get("published_at")),
            )
        return article

    def sources_for_article(self, article_id: int) -> list[ArticleSourceRecord]:
        statement = (
            select(article_sources, feeds.c.title.label("feed_title"))
            .select_from(article_sources.outerjoin(feeds, feeds.c.id == article_sources.c.feed_id))
            .where(article_sources.c.article_id == article_id)
            .order_by(article_sources.c.feed_id.asc(), article_sources.c.miniflux_entry_id.asc())
        )
        with self.engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()
        return [_source_from_row(row) for row in rows]

    def list_articles(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        user_id: UUID | None = None,
        module: str = "all",
        q: str | None = None,
        sort: str | None = None,
        score_lookup: Callable[[list[int]], Mapping[int, object]] | None = None,
    ) -> ArticlePage:
        del score_lookup
        list_module = normalize_list_module(module)
        rank_sort = resolve_rank_sort(sort, module)
        query = (q or "").strip()
        statement = _article_select()
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(
                    articles.c.title.ilike(pattern),
                    articles.c.content_text.ilike(pattern),
                )
            )
        if list_module != "all":
            if user_id is None:
                raise ValueError("user_id is required for non-all list modules")
            state_on = and_(
                user_article_states.c.article_id == articles.c.id,
                user_article_states.c.user_id == user_id,
            )
            statement = statement.outerjoin(user_article_states, state_on)
            if list_module == "unread":
                statement = statement.where(
                    or_(
                        user_article_states.c.user_id.is_(None),
                        user_article_states.c.status == "unread",
                    )
                )
            elif list_module == "read":
                statement = statement.where(user_article_states.c.status == "read")
            elif list_module == "starred":
                statement = statement.where(user_article_states.c.saved.is_(True))
            elif list_module == "read-later":
                statement = statement.where(
                    user_article_states.c.status == "unread",
                    user_article_states.c.read_progress > 0,
                    user_article_states.c.read_progress < 1,
                )
            elif list_module == "project":
                statement = statement.where(user_article_states.c.project.is_(True))
        rank_expression = None
        if rank_sort is not None:
            rank_expression = _database_rank_expression(rank_sort).label("_rank_value")
            statement = statement.add_columns(rank_expression).outerjoin(
                article_base_scores,
                and_(
                    article_base_scores.c.article_id == articles.c.id,
                    article_base_scores.c.is_active.is_(True),
                ),
            )
        if cursor and rank_sort is not None:
            cursor_rank, cursor_id = decode_ranked_article_cursor(
                cursor,
                sort_key=rank_sort,
            )
            statement = statement.where(
                (rank_expression < cursor_rank)
                | and_(rank_expression == cursor_rank, articles.c.id < cursor_id)
            )
        elif cursor:
            cursor_published_at, cursor_id = decode_article_cursor(cursor)
            if cursor_published_at is None:
                statement = statement.where(articles.c.id < cursor_id)
            else:
                statement = statement.where(
                    (articles.c.published_at < cursor_published_at)
                    | and_(
                        articles.c.published_at == cursor_published_at,
                        articles.c.id < cursor_id,
                    )
                )
        if rank_expression is not None:
            statement = statement.order_by(desc(rank_expression), desc(articles.c.id))
        else:
            statement = statement.order_by(desc(articles.c.published_at), desc(articles.c.id))
        statement = statement.limit(limit + 1)
        with self.engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()
        items = [_article_from_row(row) for row in rows[:limit]]
        has_more = len(rows) > limit
        if has_more and items and rank_sort is not None:
            next_cursor = encode_ranked_article_cursor(
                rank_sort,
                float(rows[limit - 1]["_rank_value"]),
                items[-1].id,
            )
        else:
            next_cursor = encode_article_cursor(items[-1]) if has_more and items else None
        return ArticlePage(items=items, next_cursor=next_cursor, has_more=has_more)

    def count_articles(self) -> int:
        with self.engine.begin() as connection:
            return int(connection.execute(select(func.count()).select_from(articles)).scalar_one())

    def get_article(self, article_id: int) -> ArticleRecord | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(_article_select().where(articles.c.id == article_id))
                .mappings()
                .one_or_none()
            )
        return _article_from_row(row) if row is not None else None

    def get_articles(self, article_ids: list[int]) -> dict[int, ArticleRecord]:
        unique_article_ids = _unique_article_ids(article_ids)
        if not unique_article_ids:
            return {}
        with self.engine.begin() as connection:
            rows = (
                connection.execute(_article_select().where(articles.c.id.in_(unique_article_ids)))
                .mappings()
                .all()
            )
        return {int(row["id"]): _article_from_row(row) for row in rows}

    def get_state(self, user_id: UUID, article_id: int) -> ArticleStateRecord:
        return self.get_states(user_id, [article_id])[article_id]

    def list_annotations(self, user_id: UUID, article_id: int) -> list[AnnotationRecord]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(article_annotations)
                    .where(
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.article_id == article_id,
                        article_annotations.c.deleted_at.is_(None),
                    )
                    .order_by(desc(article_annotations.c.id))
                )
                .mappings()
                .all()
            )
        return [_annotation_from_row(row) for row in rows]

    def list_annotations_for_articles(
        self,
        user_id: UUID,
        article_ids: list[int],
    ) -> dict[int, list[AnnotationRecord]]:
        if not article_ids:
            return {}
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(article_annotations)
                    .where(
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.article_id.in_(article_ids),
                        article_annotations.c.deleted_at.is_(None),
                    )
                    .order_by(
                        article_annotations.c.article_id.asc(),
                        desc(article_annotations.c.id),
                    )
                )
                .mappings()
                .all()
            )
        grouped: dict[int, list[AnnotationRecord]] = defaultdict(list)
        for row in rows:
            record = _annotation_from_row(row)
            grouped[record.article_id].append(record)
        return dict(grouped)

    def list_recent_annotations(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
    ) -> list[AnnotationRecord]:
        capped = max(1, min(limit, 100))
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(article_annotations)
                    .where(
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.deleted_at.is_(None),
                    )
                    .order_by(
                        desc(article_annotations.c.created_at),
                        desc(article_annotations.c.id),
                    )
                    .limit(capped)
                )
                .mappings()
                .all()
            )
        return [_annotation_from_row(row) for row in rows]

    def list_due_annotations(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[AnnotationRecord]:
        capped = max(1, min(limit, 100))
        moment = now or datetime.now(UTC)
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(article_annotations)
                    .where(
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.deleted_at.is_(None),
                        or_(
                            article_annotations.c.next_review_at.is_(None),
                            article_annotations.c.next_review_at <= moment,
                        ),
                    )
                    .order_by(
                        article_annotations.c.next_review_at.asc().nullsfirst(),
                        article_annotations.c.id.asc(),
                    )
                    .limit(capped)
                )
                .mappings()
                .all()
            )
        return [_annotation_from_row(row) for row in rows]

    def search_annotations(
        self,
        user_id: UUID,
        *,
        q: str,
        limit: int = 30,
    ) -> list[AnnotationRecord]:
        needle = (q or "").strip().casefold()
        if not needle:
            return []
        capped = max(1, min(limit, 100))
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(article_annotations)
                    .where(
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.deleted_at.is_(None),
                    )
                    .order_by(desc(article_annotations.c.id))
                )
                .mappings()
                .all()
            )
        records = [_annotation_from_row(row) for row in rows]
        return [
            record
            for record in records
            if needle in searchable_annotation_body(record.content).casefold()
            or needle in (record.selected_text or "").casefold()
        ][:capped]

    def get_annotation(self, user_id: UUID, annotation_id: int) -> AnnotationRecord | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(article_annotations).where(
                        article_annotations.c.id == annotation_id,
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return _annotation_from_row(row)

    def update_annotation(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        content: str,
    ) -> AnnotationRecord | None:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    article_annotations.update()
                    .where(
                        article_annotations.c.id == annotation_id,
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.deleted_at.is_(None),
                    )
                    .values(content=content, updated_at=now)
                    .returning(article_annotations)
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return _annotation_from_row(row)

    def soft_delete_annotation(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        delete_reason: str = "user_request",
    ) -> AnnotationDeleteResult:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            if self._annotation_delete_transaction_observer is not None:
                self._annotation_delete_transaction_observer(connection)
            row = (
                connection.execute(
                    article_annotations.update()
                    .where(
                        article_annotations.c.id == annotation_id,
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.deleted_at.is_(None),
                    )
                    .values(
                        deleted_at=now,
                        deleted_by=user_id,
                        delete_reason=delete_reason,
                        updated_at=now,
                    )
                    .returning(article_annotations.c.id)
                )
                .first()
            )
            if row is not None:
                return AnnotationDeleteResult.DELETED
            tombstone_id = connection.execute(
                select(article_annotations.c.id).where(
                    article_annotations.c.id == annotation_id,
                    article_annotations.c.user_id == user_id,
                    article_annotations.c.deleted_at.is_not(None),
                )
            ).scalar_one_or_none()
        if tombstone_id is not None:
            return AnnotationDeleteResult.ALREADY_DELETED
        return AnnotationDeleteResult.NOT_FOUND_OR_NOT_OWNER

    def update_annotation_review(
        self,
        user_id: UUID,
        annotation_id: int,
        *,
        next_review_at: datetime,
        interval_days: int,
        review_count: int,
    ) -> AnnotationRecord | None:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    article_annotations.update()
                    .where(
                        article_annotations.c.id == annotation_id,
                        article_annotations.c.user_id == user_id,
                        article_annotations.c.deleted_at.is_(None),
                    )
                    .values(
                        next_review_at=next_review_at,
                        interval_days=interval_days,
                        review_count=review_count,
                        updated_at=now,
                    )
                    .returning(article_annotations)
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return _annotation_from_row(row)

    def create_annotation(
        self,
        user_id: UUID,
        article_id: int,
        *,
        content: str,
        selected_text: str | None = None,
        annotation_type: str = "annotation",
    ) -> AnnotationRecord | None:
        from app.domain.spaced_review import initial_review_schedule

        if self.get_article(article_id) is None:
            return None
        if annotation_type not in {"annotation", "comment", "review"}:
            raise ValueError("unsupported annotation type")
        now = datetime.now(UTC)
        schedule = initial_review_schedule(now)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    article_annotations.insert()
                    .values(
                        article_id=article_id,
                        user_id=user_id,
                        type=annotation_type,
                        selected_text=selected_text,
                        content=content,
                        created_at=now,
                        updated_at=now,
                        next_review_at=schedule.next_review_at,
                        interval_days=schedule.interval_days,
                        review_count=schedule.review_count,
                    )
                    .returning(article_annotations)
                )
                .mappings()
                .one()
            )
        return _annotation_from_row(row)

    def get_states(self, user_id: UUID, article_ids: list[int]) -> dict[int, ArticleStateRecord]:
        unique_article_ids = _unique_article_ids(article_ids)
        if not unique_article_ids:
            return {}
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(user_article_states).where(
                        user_article_states.c.user_id == user_id,
                        user_article_states.c.article_id.in_(unique_article_ids),
                    )
                )
                .mappings()
                .all()
            )
        states = {int(row["article_id"]): _state_from_row(row) for row in rows}
        return {
            article_id: states.get(article_id, _default_state())
            for article_id in unique_article_ids
        }

    def upsert_state(
        self,
        user_id: UUID,
        article_id: int,
        *,
        status: str | None = None,
        saved: bool | None = None,
        project: bool | None = None,
        read_progress: float | None = None,
    ) -> ArticleStateRecord | None:
        if self.get_article(article_id) is None:
            return None
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                # Each update field is computed against the row that wins the
                # conflict, not a prior Python read. This prevents independent
                # status/saved writes from clobbering each other under load.
                incoming_status = bindparam("incoming_state_status", status)
                incoming_saved = bindparam("incoming_state_saved", saved)
                incoming_project = bindparam("incoming_state_project", project)
                incoming_progress = bindparam("incoming_state_progress", read_progress)
                next_saved = func.coalesce(incoming_saved, user_article_states.c.saved)
                next_project = case(
                    (incoming_saved.is_(False), False),
                    else_=func.coalesce(incoming_project, user_article_states.c.project),
                )
                row = (
                    connection.execute(
                        pg_insert(user_article_states)
                        .values(
                            user_id=user_id,
                            article_id=article_id,
                            status=func.coalesce(incoming_status, "unread"),
                            saved=func.coalesce(incoming_saved, False),
                            project=func.coalesce(incoming_project, False),
                            read_progress=incoming_progress,
                            updated_at=datetime.now(UTC),
                        )
                        .on_conflict_do_update(
                            index_elements=[
                                user_article_states.c.user_id,
                                user_article_states.c.article_id,
                            ],
                            set_={
                                "status": func.coalesce(incoming_status, user_article_states.c.status),
                                "saved": next_saved,
                                "project": next_project,
                                "read_progress": func.coalesce(incoming_progress, user_article_states.c.read_progress),
                                "updated_at": datetime.now(UTC),
                            },
                        )
                        .returning(user_article_states)
                    )
                    .mappings()
                    .one()
                )
            else:
                current = self.get_state(user_id, article_id)
                next_saved = saved if saved is not None else current.saved
                next_project = False if next_saved is False else project if project is not None else current.project
                values = {
                    "user_id": user_id,
                    "article_id": article_id,
                    "status": status if status is not None else current.status,
                    "saved": next_saved,
                    "project": next_project,
                    "read_progress": read_progress if read_progress is not None else current.read_progress,
                    "updated_at": datetime.now(UTC),
                }
                row = self._upsert_state_generic(connection, values)
        return _state_from_row(row)

    def get_feedback(self, user_id: UUID, article_id: int) -> ArticleFeedbackRecord | None:
        return self.get_feedbacks(user_id, [article_id]).get(article_id)

    def get_feedbacks(
        self,
        user_id: UUID,
        article_ids: list[int],
    ) -> dict[int, ArticleFeedbackRecord]:
        unique_article_ids = _unique_article_ids(article_ids)
        if not unique_article_ids:
            return {}
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(user_article_feedback_scores).where(
                        user_article_feedback_scores.c.user_id == user_id,
                        user_article_feedback_scores.c.article_id.in_(unique_article_ids),
                    )
                )
                .mappings()
                .all()
            )
        return {int(row["article_id"]): _feedback_from_row(row) for row in rows}

    def feed_governance_for_user(
        self,
        user_id: UUID,
        feed_ids: list[int],
    ) -> dict[int, dict[str, object]]:
        unique_feed_ids = sorted({int(feed_id) for feed_id in feed_ids})
        if not unique_feed_ids:
            return {}
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    select(user_feed_subscriptions).where(
                        user_feed_subscriptions.c.user_id == user_id,
                        user_feed_subscriptions.c.feed_id.in_(unique_feed_ids),
                    )
                )
                .mappings()
                .all()
            )
            quality_expr = case(
                (articles.c.content_quality == "full", 90.0),
                (articles.c.content_quality == "snippet", 40.0),
                (articles.c.content_quality == "partial", 35.0),
                (articles.c.content_quality == "blocked", 15.0),
                (articles.c.content_quality == "failed", 10.0),
                else_=55.0,
            )
            quality_rows = (
                connection.execute(
                    select(
                        article_sources.c.feed_id.label("feed_id"),
                        func.avg(quality_expr).label("quality_score"),
                    )
                    .select_from(
                        article_sources.join(articles, articles.c.id == article_sources.c.article_id)
                    )
                    .where(article_sources.c.feed_id.in_(unique_feed_ids))
                    .group_by(article_sources.c.feed_id)
                )
                .mappings()
                .all()
            )
        quality_by_feed = {
            int(row["feed_id"]): float(row["quality_score"])
            for row in quality_rows
            if row.get("feed_id") is not None
        }
        by_feed: dict[int, dict[str, object]] = {
            feed_id: {
                "hidden": False,
                "quality_score": quality_by_feed.get(feed_id, 70.0),
            }
            for feed_id in unique_feed_ids
        }
        for row in rows:
            feed_id = int(row["feed_id"])
            priority = int(row["user_priority"] or 0)
            hidden = bool(row.get("hidden", False)) or priority <= -20
            by_feed[feed_id] = {
                "hidden": hidden,
                "quality_score": quality_by_feed.get(feed_id, 70.0),
            }
        return by_feed

    def upsert_feedback(
        self,
        user_id: UUID,
        article_id: int,
        *,
        user_score: int,
        feedback_type: str,
        reason: str,
    ) -> ArticleFeedbackRecord | None:
        if self.get_article(article_id) is None:
            return None
        now = datetime.now(UTC)
        insert_values = {
            "user_id": user_id,
            "article_id": article_id,
            "user_score": user_score,
            "feedback_type": feedback_type,
            "reason": reason,
            "created_at": now,
            "updated_at": now,
        }
        update_values = {
            "user_score": user_score,
            "feedback_type": feedback_type,
            "reason": reason,
            "updated_at": now,
        }
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                row = (
                    connection.execute(
                        pg_insert(user_article_feedback_scores)
                        .values(**insert_values)
                        .on_conflict_do_update(
                            constraint="uq_feedback_user_article",
                            set_=update_values,
                        )
                        .returning(user_article_feedback_scores)
                    )
                    .mappings()
                    .one()
                )
            else:
                row = self._upsert_feedback_generic(
                    connection,
                    insert_values,
                    update_values,
                )
        return _feedback_from_row(row)

    def save_translation(
        self,
        article_id: int,
        *,
        content_zh: str | None,
        status: str | None,
        translated_at: datetime | None,
    ) -> ArticleRecord | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    update(articles)
                    .where(articles.c.id == article_id)
                    .values(
                        content_zh=content_zh,
                        content_zh_status=status,
                        translated_at=translated_at,
                        updated_at=datetime.now(UTC),
                    )
                    .returning(articles)
                )
                .mappings()
                .one_or_none()
            )
        return _article_from_row(row) if row is not None else None

    def dispose(self) -> None:
        self.engine.dispose()

    def _insert_article(self, connection, entry: dict[str, object], dedup_key: str):
        content_text = _optional_str(entry.get("content_text"))
        values = {
            "primary_feed_id": int(entry["feed_id"]),
            "title": str(entry["title"]),
            "url": str(entry["url"]),
            "canonical_url": canonicalize_url(str(entry["url"])),
            "author": _optional_str(entry.get("author")),
            "published_at": _optional_datetime(entry.get("published_at")),
            "content_text": content_text,
            "content_html": _optional_str(entry.get("content_html")),
            "content_zh": _optional_str(entry.get("content_zh")),
            "content_zh_status": _optional_str(entry.get("content_zh_status")),
            "translated_at": _optional_datetime(entry.get("translated_at")),
            "content_source": _optional_str(entry.get("content_source")),
            "content_quality": _optional_str(entry.get("content_quality")),
            "content_hash": _content_hash(content_text),
            "dedup_key": dedup_key,
            "fetched_at": _optional_datetime(entry.get("fetched_at")),
            "content_expires_at": _optional_datetime(entry.get("content_expires_at")),
        }
        if self.engine.dialect.name == "postgresql":
            row = (
                connection.execute(
                    pg_insert(articles)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=[articles.c.dedup_key],
                        index_where=articles.c.dedup_key.is_not(None),
                    )
                    .returning(articles)
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                return row
            return (
                connection.execute(select(articles).where(articles.c.dedup_key == dedup_key))
                .mappings()
                .one()
            )
        try:
            return connection.execute(articles.insert().values(**values).returning(articles)).mappings().one()
        except IntegrityError:
            return connection.execute(select(articles).where(articles.c.dedup_key == dedup_key)).mappings().one()

    def _upsert_source(
        self,
        connection,
        article_id: int,
        feed_id: int,
        miniflux_entry_id: int,
        source_url: str,
        source_title: str,
        published_at: datetime | None,
    ) -> None:
        values = {
            "article_id": article_id,
            "feed_id": feed_id,
            "miniflux_entry_id": miniflux_entry_id,
            "source_url": source_url,
            "source_title": source_title,
            "published_at": published_at,
            "last_seen_at": datetime.now(UTC),
        }
        if self.engine.dialect.name == "postgresql":
            connection.execute(
                pg_insert(article_sources)
                .values(**values)
                .on_conflict_do_update(
                    constraint="uq_article_sources_feed_entry",
                    set_=values,
                )
            )
            return
        existing = (
            connection.execute(
                select(article_sources).where(
                    article_sources.c.feed_id == feed_id,
                    article_sources.c.miniflux_entry_id == miniflux_entry_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is None:
            connection.execute(article_sources.insert().values(**values))
            return
        connection.execute(
            update(article_sources)
            .where(article_sources.c.id == existing["id"])
            .values(**values)
        )

    def _upsert_state_generic(self, connection, values: dict[str, object]):
        row = (
            connection.execute(
                select(user_article_states).where(
                    user_article_states.c.user_id == values["user_id"],
                    user_article_states.c.article_id == values["article_id"],
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return (
                connection.execute(
                    user_article_states.insert().values(**values).returning(user_article_states)
                )
                .mappings()
                .one()
            )
        return (
            connection.execute(
                update(user_article_states)
                .where(
                    user_article_states.c.user_id == values["user_id"],
                    user_article_states.c.article_id == values["article_id"],
                )
                .values(**values)
                .returning(user_article_states)
            )
            .mappings()
            .one()
        )

    def _upsert_feedback_generic(
        self,
        connection,
        insert_values: dict[str, object],
        update_values: dict[str, object],
    ):
        row = (
            connection.execute(
                select(user_article_feedback_scores).where(
                    user_article_feedback_scores.c.user_id == insert_values["user_id"],
                    user_article_feedback_scores.c.article_id == insert_values["article_id"],
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return (
                connection.execute(
                    user_article_feedback_scores.insert()
                    .values(**insert_values)
                    .returning(user_article_feedback_scores)
                )
                .mappings()
                .one()
            )
        return (
            connection.execute(
                update(user_article_feedback_scores)
                .where(
                    user_article_feedback_scores.c.user_id == insert_values["user_id"],
                    user_article_feedback_scores.c.article_id == insert_values["article_id"],
                )
                .values(**update_values)
                .returning(user_article_feedback_scores)
            )
            .mappings()
            .one()
        )


def create_article_repository(
    database_url: str | None,
    *,
    lock: RLock | None = None,
) -> ArticleStore:
    if database_url:
        return DatabaseArticleRepository(database_url)
    return MemoryArticleRepository(lock=lock)


def _database_rank_expression(sort_key: str):
    """Build the Postgres rank expression used by composite keyset paging."""
    base_score = func.coalesce(article_base_scores.c.base_score, -1).cast(Numeric)

    def dimension(name: str):
        return func.coalesce(
            article_base_scores.c.dimension_scores[name].astext.cast(Numeric),
            0,
        )

    if sort_key == "score":
        return base_score
    if sort_key in {"technical", "business", "trend"}:
        dimension_name = {
            "technical": "topic_relevance",
            "business": "actionability",
            "trend": "novelty",
        }[sort_key]
        return case(
            (article_base_scores.c.id.is_(None), -1),
            else_=dimension(dimension_name),
        )
    if sort_key in {"module:technical", "module:ai"}:
        return (dimension("topic_relevance") + dimension("information_density")) / 2
    if sort_key == "module:business":
        return dimension("actionability")
    if sort_key == "module:trend":
        return (dimension("novelty") + dimension("timeliness")) / 2
    if sort_key == "module:product":
        return (dimension("actionability") + dimension("reading_cost_fit")) / 2
    if sort_key == "module:security":
        return (dimension("source_quality") + (100 - dimension("risk_uncertainty"))) / 2
    raise ValueError(f"unsupported rank sort: {sort_key}")


def _article_select():
    source_counts = (
        select(
            article_sources.c.article_id.label("article_id"),
            func.count().label("source_count"),
        )
        .group_by(article_sources.c.article_id)
        .subquery()
    )
    return (
        select(
            articles,
            feeds.c.title.label("feed_title"),
            categories.c.id.label("category_id"),
            categories.c.name.label("category_title"),
            func.coalesce(source_counts.c.source_count, 0).label("source_count"),
        )
        .select_from(
            articles.outerjoin(feeds, feeds.c.id == articles.c.primary_feed_id)
            .outerjoin(categories, categories.c.id == feeds.c.category_id)
            .outerjoin(source_counts, source_counts.c.article_id == articles.c.id)
        )
    )


def _article_from_row(row) -> ArticleRecord:
    return ArticleRecord(
        id=row["id"],
        primary_feed_id=row["primary_feed_id"],
        title=row["title"],
        url=row["url"],
        canonical_url=row["canonical_url"],
        author=row["author"],
        published_at=row["published_at"],
        content_text=row["content_text"],
        content_html=row["content_html"],
        content_zh=row["content_zh"],
        content_zh_status=row["content_zh_status"],
        translated_at=row["translated_at"],
        content_source=row["content_source"],
        content_quality=row["content_quality"],
        content_hash=row["content_hash"],
        dedup_key=row["dedup_key"],
        fetched_at=row["fetched_at"],
        content_expires_at=row["content_expires_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        feed_title=_row_get(row, "feed_title"),
        category_id=_optional_int(_row_get(row, "category_id")),
        category_title=_row_get(row, "category_title"),
        source_count=int(_row_get(row, "source_count", 0) or 0),
    )


def _source_from_row(row) -> ArticleSourceRecord:
    return ArticleSourceRecord(
        article_id=row["article_id"],
        feed_id=row["feed_id"],
        feed_title=_row_get(row, "feed_title"),
        miniflux_entry_id=row["miniflux_entry_id"],
        source_url=row["source_url"],
        source_title=row["source_title"],
        published_at=row["published_at"],
    )


def _state_from_row(row) -> ArticleStateRecord:
    progress = row["read_progress"]
    return ArticleStateRecord(
        status=row["status"],
        saved=bool(row["saved"]),
        project=bool(row["project"]),
        read_progress=float(progress) if progress is not None else 0,
        updated_at=row["updated_at"],
    )


def _feedback_from_row(row) -> ArticleFeedbackRecord:
    return ArticleFeedbackRecord(
        user_score=int(row["user_score"]),
        feedback_type=row["feedback_type"],
        reason=row["reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _annotation_from_row(row) -> AnnotationRecord:
    interval_raw = row["interval_days"] if "interval_days" in row.keys() else 1
    review_count_raw = row["review_count"] if "review_count" in row.keys() else 0
    next_review_raw = row["next_review_at"] if "next_review_at" in row.keys() else None
    return AnnotationRecord(
        id=int(row["id"]),
        article_id=int(row["article_id"]),
        user_id=row["user_id"],
        type=str(row["type"]),
        selected_text=row["selected_text"],
        content=str(row["content"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        next_review_at=next_review_raw,
        interval_days=int(interval_raw) if interval_raw is not None else 1,
        review_count=int(review_count_raw) if review_count_raw is not None else 0,
        deleted_at=_row_get(row, "deleted_at"),
        deleted_by=_row_get(row, "deleted_by"),
        delete_reason=_row_get(row, "delete_reason"),
    )


def _default_state() -> ArticleStateRecord:
    return ArticleStateRecord(
        status="unread",
        saved=False,
        project=False,
        read_progress=0,
        updated_at=None,
    )


def _unique_article_ids(article_ids: list[int]) -> list[int]:
    return list(dict.fromkeys(article_ids))


def _content_hash(content_text: str | None) -> str | None:
    if not content_text:
        return None
    return hashlib.sha256(content_text.encode("utf-8")).hexdigest()


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _row_get(row, key: str, default: object = None) -> object:
    return row[key] if key in row else default


def _optional_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _article_matches_query(article: ArticleRecord, query: str) -> bool:
    """Case-insensitive substring match on title or body text."""
    needle = query.lower()
    if needle in article.title.lower():
        return True
    body = (article.content_text or "").lower()
    return needle in body


def _is_after_cursor(
    article: ArticleRecord,
    cursor_published_at: datetime | None,
    cursor_id: int,
) -> bool:
    published_at = article.published_at or datetime.min.replace(tzinfo=UTC)
    if cursor_published_at is None:
        return article.id < cursor_id
    return published_at < cursor_published_at or (
        published_at == cursor_published_at and article.id < cursor_id
    )

#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Purpose:
#   Prove the deployed staging AI Reader runtime chain end to end after deploy.
#
# Usage:
#   bash infra/scripts/staging-runtime-proof.sh staging
#
# Arguments:
#   $1  ENV  Must be staging. Production runtime proof is intentionally unsupported.
#
# Environment:
#   Reads DOMAIN and API/worker settings from the repository .env file and the
#   running staging containers. Deep runtime proof requires worker/API
#   LLM_PROVIDER=mock; non-mock providers skip the proof to avoid real LLM spend.
#
# Exit codes:
#   0 when non-mock providers are configured and the proof is intentionally
#   skipped, or when auth, sync, content fetch, mock scoring, recommendation
#   generation, latest Top10, and article ask SSE all succeed.
#   Non-zero on non-staging ENV, failed HTTP/DB checks, timed out jobs, or
#   missing proof artifacts.
#
# Side effects:
#   Creates/refreshes deterministic proof admin/user records, may enqueue a
#   synthetic sync job if staging has no articles, subscribes the proof user to
#   selected article feeds, and enqueues worker jobs in staging only.

set -euo pipefail

ENV="${1:?must provide environment name, expected staging}"

if [[ "$ENV" != "staging" ]]; then
    echo "staging-runtime-proof supports staging only, got: $ENV"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

set -a; source "$REPO_ROOT/.env"; set +a

PROJECT="myrss-${ENV}"
API_CONTAINER="${PROJECT}-ai-reader-api-1"
WORKER_CONTAINER="${PROJECT}-ai-reader-worker-1"
PUBLIC_URL="https://staging-ai-reader.${DOMAIN}"

echo "Runtime proof: $ENV"

# Mock provider is mandatory so CI/staging proof cannot spend real provider credits.
worker_llm_provider="$(docker exec "$WORKER_CONTAINER" printenv LLM_PROVIDER 2>/dev/null || true)"
api_llm_provider="$(docker exec "$API_CONTAINER" printenv LLM_PROVIDER 2>/dev/null || true)"
worker_llm_provider="${worker_llm_provider:-mock}"
api_llm_provider="${api_llm_provider:-mock}"
if [[ "$worker_llm_provider" != "mock" || "$api_llm_provider" != "mock" ]]; then
    echo "  skip staging runtime proof: requires API/worker LLM_PROVIDER=mock; got api=$api_llm_provider worker=$worker_llm_provider"
    echo "  reason: non-mock providers may spend real LLM credits"
    exit 0
fi
echo "  ok API/worker LLM_PROVIDER=mock"

# Run the proof from inside the API container so it uses the deployed code and network.
docker exec \
    -i \
    -e PUBLIC_ORIGIN="$PUBLIC_URL" \
    "$API_CONTAINER" \
    python - <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from http.cookies import SimpleCookie
import json
import os
import time
import urllib.error
import urllib.request

from sqlalchemy import create_engine, select, text, update

from app.core.config import get_settings
from app.core.security import SESSION_COOKIE_NAME, hash_token, new_recovery_code, new_token
from app.db.auth_store import SESSION_TTL
from app.db.models import app_users
from app.db.repositories.jobs import create_job_repository, dedupe_key_for


API_BASE = "http://127.0.0.1:8000"
PUBLIC_ORIGIN = os.environ["PUBLIC_ORIGIN"].rstrip("/")
PROOF_ADMIN_NAME = "staging-runtime-proof-admin"
PROOF_USER_NAME = "staging-runtime-proof-user"
PROOF_FEED_ID = 990_000_000_001
PROOF_ENTRY_ID = 990_000_000_001
PROOF_URL = "https://example.com/ai-reader/staging-runtime-proof"


# HTTP helpers always include the public Origin so CORS/CSRF behavior matches the browser path.
@dataclass(frozen=True)
class HttpResult:
    status: int
    payload: object
    raw: str
    headers: object


def fail(message: str) -> None:
    raise SystemExit(message)


def http_json(
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    cookie: str | None = None,
    expected: tuple[int, ...] = (200,),
    timeout: int = 15,
) -> HttpResult:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Origin": PUBLIC_ORIGIN}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if cookie is not None:
        headers["Cookie"] = f"{SESSION_COOKIE_NAME}={cookie}"

    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
            response_headers = response.headers
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        fail(f"{method} {path} returned HTTP {error.code}: {_safe_error(raw)}")

    if status not in expected:
        fail(f"{method} {path} returned HTTP {status}, expected {expected}: {_safe_error(raw)}")
    parsed = json.loads(raw) if raw else {}
    return HttpResult(status=status, payload=parsed, raw=raw, headers=response_headers)


def http_raw(
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    cookie: str | None = None,
    expected: tuple[int, ...] = (200,),
    timeout: int = 30,
) -> HttpResult:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Origin": PUBLIC_ORIGIN}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if cookie is not None:
        headers["Cookie"] = f"{SESSION_COOKIE_NAME}={cookie}"

    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
            response_headers = response.headers
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        fail(f"{method} {path} returned HTTP {error.code}: {_safe_error(raw)}")

    if status not in expected:
        fail(f"{method} {path} returned HTTP {status}, expected {expected}: {_safe_error(raw)}")
    return HttpResult(status=status, payload={}, raw=raw, headers=response_headers)


def _safe_error(raw: str) -> str:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:240]
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return f"{error.get('code')}: {error.get('message')}"
    return raw[:240]


def session_cookie_from(headers: object) -> str:
    cookie = SimpleCookie()
    get_all = getattr(headers, "get_all", None)
    values = get_all("Set-Cookie") if callable(get_all) else []
    for value in values or []:
        cookie.load(value)
    morsel = cookie.get(SESSION_COOKIE_NAME)
    if morsel is None:
        fail("auth response did not set a session cookie")
    return morsel.value


def refresh_recoverable_user(engine, *, display_name: str, role: str):
    now = datetime.now(UTC)
    recovery_code = new_recovery_code()
    values = {
        "display_name": display_name,
        "session_token_hash": hash_token(new_token()),
        "recovery_code_hash": hash_token(recovery_code),
        "role": role,
        "session_expires_at": now + SESSION_TTL,
        "recovery_rotated_at": now,
        "last_seen_at": now,
    }
    with engine.begin() as connection:
        existing = (
            connection.execute(
                select(app_users.c.id)
                .where(app_users.c.display_name == display_name, app_users.c.role == role)
                .order_by(app_users.c.created_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if existing is None:
            row = (
                connection.execute(app_users.insert().values(**values).returning(app_users.c.id))
                .mappings()
                .one()
            )
            return row["id"], recovery_code

        user_id = existing["id"]
        connection.execute(update(app_users).where(app_users.c.id == user_id).values(**values))
        return user_id, recovery_code


def recover_session(recovery_code: str, *, expected_role: str) -> str:
    response = http_json(
        "POST",
        "/api/auth/recover",
        payload={"recovery_code": recovery_code},
        expected=(200,),
    )
    payload = response.payload
    if not isinstance(payload, dict):
        fail("auth recover returned a non-object payload")
    user = payload.get("user")
    if not isinstance(user, dict) or user.get("role") != expected_role:
        fail(f"auth recover returned unexpected role for {expected_role}")
    return session_cookie_from(response.headers)


def wait_job(job_id: int, *, cookie: str, label: str, timeout_seconds: int = 120) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_status = "unknown"
    while time.monotonic() < deadline:
        response = http_json("GET", f"/api/jobs/{job_id}", cookie=cookie)
        payload = response.payload
        if not isinstance(payload, dict):
            fail(f"{label} job returned a non-object payload")
        last_status = str(payload.get("status"))
        if last_status == "succeeded":
            return payload
        if last_status in {"failed", "cancelled"}:
            fail(f"{label} job {job_id} ended as {last_status}: {payload.get('last_error')}")
        time.sleep(2)
    fail(f"{label} job {job_id} did not finish within {timeout_seconds}s; last status={last_status}")


# The fallback article keeps proof deterministic when a staging Miniflux account is empty.
def ensure_proof_feed(engine, user_id: object) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO feeds (id, feed_url, title, status)
                VALUES (:feed_id, :feed_url, 'Staging runtime proof feed', 'active')
                ON CONFLICT (id) DO UPDATE SET
                    feed_url=EXCLUDED.feed_url,
                    title=EXCLUDED.title,
                    status='active',
                    updated_at=NOW();
                """
            ),
            {
                "feed_id": PROOF_FEED_ID,
                "feed_url": "https://example.com/ai-reader/staging-runtime-proof.xml",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO user_feed_subscriptions (user_id, feed_id, enabled, user_priority)
                VALUES (:user_id, :feed_id, TRUE, 20)
                ON CONFLICT (user_id, feed_id) DO UPDATE SET
                    enabled=TRUE,
                    user_priority=20,
                    updated_at=NOW();
                """
            ),
            {"user_id": user_id, "feed_id": PROOF_FEED_ID},
        )


def enqueue_synthetic_sync(settings, *, admin_id: object) -> int:
    repository = create_job_repository(settings.database_url)
    try:
        job = repository.enqueue(
            "sync_miniflux_entries",
            {
                "entries": [
                    {
                        "feed_id": PROOF_FEED_ID,
                        "miniflux_entry_id": PROOF_ENTRY_ID,
                        "url": PROOF_URL,
                        "title": "AI Reader staging runtime proof",
                        "published_at": datetime.now(UTC).isoformat(),
                        "content_text": (
                            "This synthetic staging proof article exercises sync, fetch, "
                            "mock scoring, recommendation generation, and article ask."
                        ),
                        "content_html": (
                            "<article><p>This synthetic staging proof article exercises "
                            "sync, fetch, mock scoring, recommendation generation, and "
                            "article ask.</p></article>"
                        ),
                    }
                ]
            },
            dedupe_key=dedupe_key_for("sync_miniflux_entries", f"staging-proof-{int(time.time())}"),
            created_by=admin_id,
        )
        return int(job.id)
    finally:
        dispose = getattr(repository, "dispose", None)
        if callable(dispose):
            dispose()


def article_id_by_url(engine, url: str) -> int | None:
    with engine.begin() as connection:
        article_id = connection.execute(
            text(
                """
                SELECT id
                FROM articles
                WHERE url=:url OR canonical_url=:url
                ORDER BY id DESC
                LIMIT 1;
                """
            ),
            {"url": url},
        ).scalar_one_or_none()
    return int(article_id) if article_id is not None else None


def latest_article_id_from_api(user_cookie: str) -> int | None:
    response = http_json("GET", "/api/articles?limit=1", cookie=user_cookie)
    payload = response.payload
    if not isinstance(payload, dict):
        fail("article list returned a non-object payload")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict) or "id" not in first:
        fail("article list returned an invalid item")
    return int(first["id"])


# Recommendation proof subscribes the user to the selected feed so ranking is not incidental.
def subscribe_user_to_article_feeds(engine, *, user_id: object, article_id: int) -> int:
    with engine.begin() as connection:
        feed_ids = [
            int(row["feed_id"])
            for row in connection.execute(
                text(
                    """
                    SELECT feed_id
                    FROM article_sources
                    WHERE article_id=:article_id
                    ORDER BY feed_id;
                    """
                ),
                {"article_id": article_id},
            )
            .mappings()
            .all()
        ]
        if not feed_ids:
            primary_feed_id = connection.execute(
                text(
                    """
                    SELECT primary_feed_id
                    FROM articles
                    WHERE id=:article_id;
                    """
                ),
                {"article_id": article_id},
            ).scalar_one_or_none()
            if primary_feed_id is not None:
                feed_ids = [int(primary_feed_id)]
        if not feed_ids:
            fail(f"article {article_id} has no feed source to subscribe for proof recommendations")

        for feed_id in feed_ids:
            connection.execute(
                text(
                    """
                    INSERT INTO user_feed_subscriptions (user_id, feed_id, enabled, user_priority)
                    VALUES (:user_id, :feed_id, TRUE, 20)
                    ON CONFLICT (user_id, feed_id) DO UPDATE SET
                        enabled=TRUE,
                        user_priority=20,
                        updated_at=NOW();
                    """
                ),
                {"user_id": user_id, "feed_id": feed_id},
            )
    return len(feed_ids)


# The scoring sink should enqueue recommendation generation; this waits for that downstream job.
def find_recommendation_job_id(engine, batch_id: int, *, timeout_seconds: int = 60) -> int:
    deadline = time.monotonic() + timeout_seconds
    payload = json.dumps({"source_batch_id": batch_id})
    while time.monotonic() < deadline:
        with engine.begin() as connection:
            job_id = connection.execute(
                text(
                    """
                    SELECT id
                    FROM jobs
                    WHERE job_type='generate_recommendations'
                      AND payload @> CAST(:payload AS jsonb)
                    ORDER BY id DESC
                    LIMIT 1;
                    """
                ),
                {"payload": payload},
            ).scalar_one_or_none()
        if job_id is not None:
            return int(job_id)
        time.sleep(1)
    fail(f"no generate_recommendations job appeared for batch {batch_id}")


def result_dict(job_payload: dict[str, object]) -> dict[str, object]:
    result = job_payload.get("result")
    if not isinstance(result, dict):
        fail(f"job {job_payload.get('id')} returned a non-object result")
    return result


def main() -> None:
    settings = get_settings()
    if settings.database_url is None:
        fail("SCORING_DATABASE_URL is required for staging runtime proof")
    if settings.llm_provider.strip().lower() != "mock":
        fail(f"staging runtime proof requires API LLM_PROVIDER=mock, got: {settings.llm_provider}")

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        # Refresh fixed proof users instead of printing or reusing any long-lived secret.
        admin_id, admin_recovery_code = refresh_recoverable_user(
            engine,
            display_name=PROOF_ADMIN_NAME,
            role="admin",
        )
        user_id, user_recovery_code = refresh_recoverable_user(
            engine,
            display_name=PROOF_USER_NAME,
            role="user",
        )
        admin_cookie = recover_session(admin_recovery_code, expected_role="admin")
        user_cookie = recover_session(user_recovery_code, expected_role="user")
        print("  ok proof admin/user sessions refreshed")

        # Exercise the same admin sync endpoint used by the web admin console.
        sync_response = http_json(
            "POST",
            "/api/admin/sync",
            payload={"limit": 10},
            cookie=admin_cookie,
            expected=(202,),
        )
        if not isinstance(sync_response.payload, dict):
            fail("admin sync returned a non-object payload")
        sync_job_id = int(sync_response.payload["job_id"])
        sync_job = wait_job(sync_job_id, cookie=admin_cookie, label="admin sync")
        sync_result = result_dict(sync_job)
        print(
            "  ok admin sync job "
            f"{sync_job_id}: entries_seen={sync_result.get('entries_seen')} "
            f"articles_upserted={sync_result.get('articles_upserted')}"
        )

        # Prefer real staging articles; fall back to a synthetic feed only when staging is empty.
        article_id = latest_article_id_from_api(user_cookie)
        if article_id is None:
            ensure_proof_feed(engine, user_id)
            synthetic_job_id = enqueue_synthetic_sync(settings, admin_id=admin_id)
            synthetic_job = wait_job(synthetic_job_id, cookie=admin_cookie, label="synthetic sync")
            synthetic_result = result_dict(synthetic_job)
            article_id = article_id_by_url(engine, PROOF_URL)
            if article_id is None:
                fail("synthetic sync succeeded but proof article was not found")
            print(
                "  ok synthetic sync fallback job "
                f"{synthetic_job_id}: entries_seen={synthetic_result.get('entries_seen')} "
                f"articles_upserted={synthetic_result.get('articles_upserted')}"
            )
        else:
            print(f"  ok selected staging article id={article_id}")

        subscribed_feed_count = subscribe_user_to_article_feeds(
            engine,
            user_id=user_id,
            article_id=article_id,
        )
        print(
            "  ok proof user subscribed to selected article feeds: "
            f"feed_count={subscribed_feed_count}"
        )

        # Content fetch proves the worker can process article enrichment before scoring and ask.
        fetch_response = http_json(
            "POST",
            f"/api/articles/{article_id}/fetch-content",
            payload={},
            cookie=user_cookie,
            expected=(202,),
        )
        if not isinstance(fetch_response.payload, dict):
            fail("fetch-content returned a non-object payload")
        fetch_job_id = int(fetch_response.payload["job_id"])
        fetch_job = wait_job(fetch_job_id, cookie=user_cookie, label="content fetch")
        fetch_result = result_dict(fetch_job)
        print(
            "  ok content fetch job "
            f"{fetch_job_id}: outcome={fetch_result.get('outcome')} "
            f"content_quality={fetch_result.get('content_quality')}"
        )

        # A one-article batch keeps the proof cheap while still traversing batch and job state.
        batch_response = http_json(
            "POST",
            "/api/admin/scoring-batches",
            payload={
                "name": f"staging-runtime-proof-{int(time.time())}",
                "candidate_window": "custom",
                "article_ids": [article_id],
            },
            cookie=admin_cookie,
            expected=(201,),
        )
        if not isinstance(batch_response.payload, dict):
            fail("create scoring batch returned a non-object payload")
        batch = batch_response.payload.get("batch")
        if not isinstance(batch, dict):
            fail("create scoring batch response missing batch object")
        batch_id = int(batch["id"])

        start_response = http_json(
            "POST",
            f"/api/admin/scoring-batches/{batch_id}/start",
            payload={},
            cookie=admin_cookie,
            expected=(202,),
        )
        if not isinstance(start_response.payload, dict):
            fail("start scoring batch returned a non-object payload")
        score_job_id = int(start_response.payload["job_id"])
        score_job = wait_job(score_job_id, cookie=admin_cookie, label="mock scoring")
        score_result = result_dict(score_job)
        if int(score_result.get("scores_saved", 0)) < 1:
            fail(f"mock scoring job {score_job_id} did not save any score")
        print(
            "  ok mock scoring batch "
            f"{batch_id} job {score_job_id}: scores_saved={score_result.get('scores_saved')} "
            f"scores_failed={score_result.get('scores_failed')}"
        )

        # Recommendations are the required downstream effect of a successful scoring batch.
        recommendation_job_id = find_recommendation_job_id(engine, batch_id)
        recommendation_job = wait_job(
            recommendation_job_id,
            cookie=admin_cookie,
            label="recommendations",
        )
        recommendation_result = result_dict(recommendation_job)
        if int(recommendation_result.get("editions_saved", 0)) < 1:
            fail(f"recommendations job {recommendation_job_id} did not save an edition")
        print(
            "  ok recommendations job "
            f"{recommendation_job_id}: editions_saved={recommendation_result.get('editions_saved')} "
            f"users_seen={recommendation_result.get('users_seen')}"
        )

        latest_response = http_json("GET", "/api/recommendations/latest", cookie=user_cookie)
        latest = latest_response.payload
        if not isinstance(latest, dict) or latest.get("edition") is None:
            fail("latest recommendations did not return an edition for the proof user")
        items = latest.get("items")
        if not isinstance(items, list) or not items:
            fail("latest recommendations returned an empty item list")
        edition = latest["edition"]
        edition_id = edition.get("id") if isinstance(edition, dict) else "unknown"
        print(f"  ok latest recommendations edition {edition_id}: items={len(items)}")

        # Ask SSE proves the user-facing streaming path sees the same article context.
        ask_response = http_raw(
            "POST",
            f"/api/articles/{article_id}/ask",
            payload={"question": "Summarize this article in one sentence."},
            cookie=user_cookie,
            expected=(200,),
            timeout=45,
        )
        if "event: done" not in ask_response.raw or "data:" not in ask_response.raw:
            fail("ask SSE response did not include data and done events")
        print(f"  ok ask SSE streamed {len(ask_response.raw)} bytes")
    finally:
        engine.dispose()

    print("Runtime proof passed: staging")


if __name__ == "__main__":
    main()
PY

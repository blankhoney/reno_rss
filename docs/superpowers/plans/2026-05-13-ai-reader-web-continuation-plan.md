# AI Reader Web Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue the AI Reader Web work in small, reviewable iterations that stabilize the reading loop before adding deployment and Agent UI polish.

**Architecture:** Use the existing `feat/ai-reader-web` worktree as the continuation baseline. Keep Miniflux as the RSS source of truth, keep scoring data in PostgreSQL, and make `reader-web` reliable by fixing filtering, state, fallback behavior, and repository hygiene before expanding the UI. Deployment wiring is allowed only after local test/build verification passes; Agent panel work is explicitly outside this continuation plan.

**Tech Stack:** Next.js App Router, React, TypeScript, Node test runner, PostgreSQL `pg`, Python scorer-worker, Docker Compose, Caddy, Authelia.

---

## Baseline

Use this worktree:

```bash
cd /Users/blankhoney/workspace/project2026/my_rss/.worktrees/ai-reader-web
git status --short --branch
```

Expected branch: `feat/ai-reader-web`.

Do not continue reader-web feature work from the root `main` worktree until this branch is reviewed and merged. The root `main` worktree is behind the real reader-web implementation.

## Scope Rules

- Prefer one task per commit.
- Do not add new product surface while fixing correctness or safety bugs.
- Keep feed management and Agent UI behind the core reading loop unless a task explicitly touches them.
- Do not modify generated files except to remove them from Git tracking.
- Do not clean unrelated user changes unless explicitly instructed.

## File Structure

- `.gitignore`: ignore generated Python, Node, and Next.js outputs.
- `apps/reader-web/src/lib/articles/service.ts`: article module filtering, Miniflux query selection, sorting helpers.
- `apps/reader-web/src/lib/articles/service.test.ts`: unit tests for module filtering and Miniflux filter selection.
- `apps/reader-web/src/app/api/articles/route.ts`: list endpoint wiring, scoring fallback, reader state merge.
- `apps/reader-web/src/lib/scoring/repository.ts`: reader state SQL helpers, including read timestamps.
- `apps/reader-web/src/lib/scoring/repository.test.ts`: SQL-shape tests for reader state writes.
- `apps/reader-web/src/components/ArticleReader.tsx`: state action integration only when needed by the reading loop.
- `apps/reader-web/src/app/globals.css`: only UI styles needed by the touched components.
- `.github/workflows/ci.yml`: add reader-web test/build checks.
- `.env.example`, `infra/compose/*.yml`, `infra/caddy/conf.d/reader-web.caddy`: deployment wiring when the reading loop is stable.
- `docs/learning-notes.md`: short learning note after each milestone.

---

## Task 1: Clean Generated File Tracking

**Files:**
- Modify: `.gitignore`
- Git index cleanup: tracked files under `apps/scorer-worker/**/__pycache__/`

- [ ] **Step 1: Extend `.gitignore`**

Add these entries:

```gitignore
# Python generated files
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
*.egg-info/

# Node / Next.js generated files
node_modules/
.next/
```

- [ ] **Step 2: Remove generated Python cache files from Git tracking**

Run:

```bash
git rm --cached -r apps/scorer-worker/src/__pycache__ apps/scorer-worker/tests/__pycache__
```

Expected: Git stages deletions for tracked `.pyc` files only. Source files must not be removed from disk.

- [ ] **Step 3: Verify status**

Run:

```bash
git status --short
```

Expected: `.gitignore` modified, tracked `__pycache__` files staged for deletion, and no new generated files listed from `node_modules`, `.next`, or `__pycache__`.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: stop tracking generated files"
```

---

## Task 2: Stabilize Module Filtering and Reader State

**Files:**
- Modify: `apps/reader-web/src/lib/articles/service.ts`
- Modify: `apps/reader-web/src/lib/articles/service.test.ts`
- Modify: `apps/reader-web/src/app/api/articles/route.ts`
- Modify: `apps/reader-web/src/lib/scoring/repository.ts`
- Modify: `apps/reader-web/src/lib/scoring/repository.test.ts`
- Modify: `apps/reader-web/src/app/api/articles/[id]/read/route.ts`

- [ ] **Step 1: Add failing module filtering tests**

Update the import section in `apps/reader-web/src/lib/articles/service.test.ts` so it imports `Article`, `filterArticlesForModule`, `minifluxEntryFilterForModule`, and `sortArticlesForModule`, then append the test helper and tests:

```ts
import type { Article } from "./types";
import {
  filterArticlesForModule,
  minifluxEntryFilterForModule,
  sortArticlesForModule,
} from "./service";

function article(
  id: number,
  input: Partial<Article> & { overall?: number } = {},
): Article {
  const overall = input.overall ?? 50;
  return {
    id,
    userId: input.userId ?? 7,
    feedId: input.feedId ?? 1,
    feedTitle: input.feedTitle ?? "Feed",
    categoryId: input.categoryId ?? 1,
    categoryTitle: input.categoryTitle ?? "AI",
    title: input.title ?? `Article ${id}`,
    url: input.url ?? "https://example.com",
    contentHtml: input.contentHtml ?? "<p>Body</p>",
    status: input.status ?? "unread",
    starred: input.starred ?? false,
    publishedAt: input.publishedAt ?? "2026-05-13T00:00:00.000Z",
    score: input.score ?? {
      overall,
      dimensions: {
        importance: overall,
        usefulness: overall,
        timeliness: overall,
        depth: overall,
        technical_value: overall,
        business_value: overall,
        trend_value: overall,
      },
      tags: [],
      reason: "",
      scoredAt: null,
    },
    readLater: input.readLater ?? false,
    lastReadAt: input.lastReadAt ?? null,
  };
}

test("minifluxEntryFilterForModule fetches all statuses for starred and read-later", () => {
  assert.deepEqual(minifluxEntryFilterForModule("starred", 25), {
    status: "all",
    starred: true,
    limit: 25,
  });
  assert.deepEqual(minifluxEntryFilterForModule("read-later", 25), {
    status: "all",
    starred: undefined,
    limit: 25,
  });
});

test("filterArticlesForModule keeps only read-later items for read-later module", () => {
  const filtered = filterArticlesForModule(
    [article(1, { readLater: false }), article(2, { readLater: true })],
    "read-later",
  );
  assert.deepEqual(filtered.map((item) => item.id), [2]);
});

test("read module sorts by most recent lastReadAt", () => {
  const sorted = sortArticlesForModule(
    [
      article(1, { status: "read", lastReadAt: "2026-05-12T00:00:00.000Z" }),
      article(2, { status: "read", lastReadAt: "2026-05-13T00:00:00.000Z" }),
    ],
    "read",
  );
  assert.deepEqual(sorted.map((item) => item.id), [2, 1]);
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/articles/service.test.ts
```

Expected: FAIL because `filterArticlesForModule` and `minifluxEntryFilterForModule` are not exported yet.

- [ ] **Step 3: Implement module filter helpers**

In `apps/reader-web/src/lib/articles/service.ts`, add:

```ts
export type MinifluxEntryModuleFilter = {
  status: "read" | "unread" | "all";
  starred?: boolean;
  limit: number;
};

export function minifluxEntryFilterForModule(
  moduleId: ModuleId,
  limit: number,
): MinifluxEntryModuleFilter {
  if (moduleId === "read") return { status: "read", starred: undefined, limit };
  if (moduleId === "starred") return { status: "all", starred: true, limit };
  if (moduleId === "read-later") return { status: "all", starred: undefined, limit };
  return { status: "unread", starred: undefined, limit };
}

export function filterArticlesForModule(articles: Article[], moduleId: ModuleId): Article[] {
  if (moduleId === "read-later") return articles.filter((article) => article.readLater);
  return articles;
}
```

- [ ] **Step 4: Wire list API through the helpers and degrade when scoring DB is unavailable**

In `apps/reader-web/src/app/api/articles/route.ts`, replace the local status/starred logic with:

```ts
const minifluxFilter = minifluxEntryFilterForModule(moduleId, limit);
const baseArticles = await miniflux.getEntries(minifluxFilter);
```

Wrap scoring and reader state reads with fallback:

```ts
let scores = new Map<number, ArticleScore>();
let states = new Map<number, { readLater: boolean; lastReadAt: string | null }>();
try {
  const pool = getPool();
  [scores, states] = await Promise.all([
    getScoresByEntryIds(pool, config.READER_TENANT_ID, entryIds),
    getReaderStatesByEntryIds(pool, config.READER_TENANT_ID, minifluxUserId, entryIds),
  ]);
} catch {
  scores = new Map();
  states = new Map();
}

const articles = sortArticlesForModule(
  filterArticlesForModule(mergeArticleData(baseArticles, scores, states), moduleId),
  moduleId,
);
```

Import `ArticleScore`, `filterArticlesForModule`, and `minifluxEntryFilterForModule` as needed.

- [ ] **Step 5: Add reader state SQL helper tests for marking read**

Update the import section in `apps/reader-web/src/lib/scoring/repository.test.ts` to include `markReadSql`, then append:

```ts
import { markReadSql } from "./repository";

test("markReadSql upserts last_read_at without changing read_later", () => {
  const query = markReadSql({
    tenantId: "default",
    minifluxUserId: 7,
    minifluxEntryId: 42,
  });

  assert.equal(query.values[0], "default");
  assert.equal(query.values[1], 7);
  assert.equal(query.values[2], 42);
  assert.match(query.text, /last_read_at/);
  assert.match(query.text, /ON CONFLICT/);
  assert.doesNotMatch(query.text, /read_later\s*=/);
});
```

- [ ] **Step 6: Implement read timestamp helper**

Add to `apps/reader-web/src/lib/scoring/repository.ts`:

```ts
export function markReadSql(input: {
  tenantId: string;
  minifluxUserId: number;
  minifluxEntryId: number;
}) {
  return {
    text: `
      INSERT INTO reader_entry_states (
        tenant_id, miniflux_user_id, miniflux_entry_id, last_read_at, updated_at
      )
      VALUES ($1, $2, $3, NOW(), NOW())
      ON CONFLICT (tenant_id, miniflux_user_id, miniflux_entry_id)
      DO UPDATE SET
        last_read_at = NOW(),
        updated_at = NOW()
    `,
    values: [input.tenantId, input.minifluxUserId, input.minifluxEntryId],
  };
}

export async function markRead(
  pool: Pool,
  tenantId: string,
  minifluxUserId: number,
  minifluxEntryId: number,
): Promise<void> {
  const { text, values } = markReadSql({ tenantId, minifluxUserId, minifluxEntryId });
  await pool.query(text, values);
}
```

- [ ] **Step 7: Wire `POST /api/articles/[id]/read` to update reader state**

In `apps/reader-web/src/app/api/articles/[id]/read/route.ts`, after Miniflux is updated, call:

```ts
const config = getConfig();
await markRead(
  getPool(),
  config.READER_TENANT_ID,
  config.READER_MINIFLUX_USER_ID,
  id,
);
```

If the state write fails after Miniflux succeeds, return HTTP 207 with `{ ok: true, warning: "reader_state_update_failed" }` rather than failing the whole request.

- [ ] **Step 8: Run verification**

```bash
cd apps/reader-web
npm test -- src/lib/articles/service.test.ts src/lib/scoring/repository.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/reader-web/src/lib/articles/service.ts \
  apps/reader-web/src/lib/articles/service.test.ts \
  apps/reader-web/src/app/api/articles/route.ts \
  apps/reader-web/src/app/api/articles/[id]/read/route.ts \
  apps/reader-web/src/lib/scoring/repository.ts \
  apps/reader-web/src/lib/scoring/repository.test.ts
git commit -m "fix(reader-web): stabilize article module state"
```

---

## Task 3: Add Minimal HTML Safety for RSS Content

**Files:**
- Modify: `apps/reader-web/package.json`
- Modify: `apps/reader-web/src/lib/articles/service.ts`
- Modify: `apps/reader-web/src/lib/articles/service.test.ts`

- [ ] **Step 1: Add sanitizer dependency**

Run:

```bash
cd apps/reader-web
npm install isomorphic-dompurify
```

Expected: `package.json` and `package-lock.json` change.

- [ ] **Step 2: Add failing sanitizer test**

Update the import section in `apps/reader-web/src/lib/articles/service.test.ts` to include `sanitizeArticleHtml`, then append:

```ts
import { sanitizeArticleHtml } from "./service";

test("sanitizeArticleHtml removes script tags and inline event handlers", () => {
  const html = sanitizeArticleHtml('<p onclick="bad()">Hi</p><script>alert(1)</script>');
  assert.equal(html.includes("<script"), false);
  assert.equal(html.includes("onclick"), false);
  assert.match(html, /Hi/);
});
```

- [ ] **Step 3: Implement sanitizer helper and use it during merge**

In `apps/reader-web/src/lib/articles/service.ts`, add:

```ts
import DOMPurify from "isomorphic-dompurify";

export function sanitizeArticleHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  });
}
```

Then in `mergeArticleData`, change `contentHtml` assignment by returning:

```ts
return {
  ...article,
  contentHtml: sanitizeArticleHtml(article.contentHtml),
  score: scores.get(article.id) ?? null,
  readLater: state?.readLater ?? false,
  lastReadAt: state?.lastReadAt ?? null,
};
```

- [ ] **Step 4: Run verification**

```bash
cd apps/reader-web
npm test -- src/lib/articles/service.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/reader-web/package.json apps/reader-web/package-lock.json apps/reader-web/src/lib/articles/service.ts apps/reader-web/src/lib/articles/service.test.ts
git commit -m "fix(reader-web): sanitize RSS article HTML"
```

---

## Task 4: Add Reader Web CI Without Expanding Scope

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add Node setup and reader-web checks**

Add after Python unit tests in `.github/workflows/ci.yml`:

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: apps/reader-web/package-lock.json

      - name: Install reader-web dependencies
        working-directory: apps/reader-web
        run: npm ci

      - name: Reader web tests
        working-directory: apps/reader-web
        run: npm test

      - name: Reader web build
        working-directory: apps/reader-web
        run: npm run build
```

- [ ] **Step 2: Keep lint out unless it is migrated**

Do not add `npm run lint` in this task. The current script is `next lint`, and Next.js lint support is unstable across major versions. ESLint CLI migration is outside this continuation plan.

- [ ] **Step 3: Run local verification**

```bash
cd apps/reader-web
npm ci
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: verify reader web"
```

---

## Task 5: Wire Deployment Only After Local Reading Loop Is Stable

**Files:**
- Modify: `.env.example`
- Modify: `infra/compose/docker-compose.base.yml`
- Modify: `infra/compose/docker-compose.prod.yml`
- Modify: `infra/compose/docker-compose.staging.yml`
- Create: `infra/caddy/conf.d/reader-web.caddy`

- [ ] **Step 1: Add required reader-web env template**

Add to `.env.example`:

```dotenv
READER_TENANT_ID=default
READER_MINIFLUX_USER_ID=1
WEB_SEARCH_PROVIDER=none
WEB_SEARCH_API_KEY=change_me
AI_READER_HOST=ai-reader
STAGING_AI_READER_HOST=staging-ai-reader
```

- [ ] **Step 2: Add `reader-web` service**

In `infra/compose/docker-compose.base.yml`, add:

```yaml
  reader-web:
    build:
      context: ../../apps/reader-web
    restart: unless-stopped
    environment:
      MINIFLUX_API_BASE_URL: ${MINIFLUX_API_BASE_URL}
      MINIFLUX_USERNAME: ${MINIFLUX_ADMIN}
      MINIFLUX_PASSWORD: ${MINIFLUX_ADMIN_PASSWORD}
      SCORING_DATABASE_URL: ${SCORING_DATABASE_URL}
      READER_TENANT_ID: ${READER_TENANT_ID}
      READER_MINIFLUX_USER_ID: ${READER_MINIFLUX_USER_ID}
      MINIMAX_API_KEY: ${MINIMAX_API_KEY}
      MINIMAX_BASE_URL: ${MINIMAX_BASE_URL}
      MINIMAX_MODEL: ${MINIMAX_MODEL}
      WEB_SEARCH_PROVIDER: ${WEB_SEARCH_PROVIDER}
      WEB_SEARCH_API_KEY: ${WEB_SEARCH_API_KEY}
    networks:
      - app
      - data
```

- [ ] **Step 3: Add prod and staging aliases**

In `infra/compose/docker-compose.prod.yml`:

```yaml
  reader-web:
    networks:
      app:
        aliases:
          - reader-web-prod
      data: {}
```

In `infra/compose/docker-compose.staging.yml`:

```yaml
  reader-web:
    networks:
      app:
        aliases:
          - reader-web-staging
      data: {}
```

- [ ] **Step 4: Add Caddy route**

Create `infra/caddy/conf.d/reader-web.caddy`:

```caddyfile
ai-reader.{$DOMAIN} {
    handle {
        forward_auth authelia-prod:9091 {
            uri /api/authz/forward-auth
            copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
        }
        reverse_proxy reader-web-prod:3000
    }
}

staging-ai-reader.{$DOMAIN} {
    handle {
        forward_auth authelia-staging:9091 {
            uri /api/authz/forward-auth
            copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
        }
        reverse_proxy reader-web-staging:3000
    }
}
```

- [ ] **Step 5: Validate Compose config**

```bash
docker compose \
  --env-file .env.example \
  -f infra/compose/docker-compose.base.yml \
  -f infra/compose/docker-compose.prod.yml \
  config >/tmp/myrss-reader-web-prod.yml

rg "reader-web|reader-web-prod|READER_MINIFLUX_USER_ID" /tmp/myrss-reader-web-prod.yml
```

Expected: command exits 0 and the generated config contains `reader-web`, `reader-web-prod`, and `READER_MINIFLUX_USER_ID`.

- [ ] **Step 6: Commit**

```bash
git add .env.example infra/compose/docker-compose.base.yml infra/compose/docker-compose.prod.yml infra/compose/docker-compose.staging.yml infra/caddy/conf.d/reader-web.caddy
git commit -m "feat(infra): route reader web"
```

---

## Out of Scope for This Continuation

Do not implement Agent panel UI in this plan. Open a new plan after Tasks 1-5 pass and after reader-web is either merged or deployed to staging.

Minimum acceptance criteria for that separate Agent UI plan:

- The panel appears only when an article is selected.
- It posts to `POST /api/agent/article-chat`.
- It sends `question`, `selectedText`, and a compact article payload.
- It shows streaming text incrementally.
- It displays a clear error when the Agent route returns non-2xx.
- It does not block opening the original article or reading the content.

First test for that separate plan:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { buildArticleAgentPayload } from "./payload";

test("buildArticleAgentPayload keeps selected text and compact article context", () => {
  const payload = buildArticleAgentPayload({
    article: {
      id: 1,
      title: "Example",
      url: "https://example.com",
      contentHtml: "<p>Hello world</p>",
      score: {
        overall: 80,
        dimensions: {
          importance: 80,
          usefulness: 80,
          timeliness: 80,
          depth: 80,
          technical_value: 80,
          business_value: 80,
          trend_value: 80,
        },
        tags: ["ai"],
        reason: "Useful.",
        scoredAt: null,
      },
      userId: 7,
      feedId: 1,
      feedTitle: "Feed",
      categoryId: 1,
      categoryTitle: "AI",
      status: "unread",
      starred: false,
      publishedAt: null,
      readLater: false,
      lastReadAt: null,
    },
    question: "解释这段",
    selectedText: "Hello",
  });

  assert.equal(payload.question, "解释这段");
  assert.equal(payload.selectedText, "Hello");
  assert.equal(payload.article.title, "Example");
  assert.match(payload.article.contentText, /Hello world/);
});
```

---

## Verification Before Merge

Run from `/Users/blankhoney/workspace/project2026/my_rss/.worktrees/ai-reader-web`:

```bash
cd apps/scorer-worker
python -m pytest tests -q
ruff check src

cd ../reader-web
npm ci
npm test
npm run build

cd ../..
docker compose \
  --env-file .env.example \
  -f infra/compose/docker-compose.base.yml \
  -f infra/compose/docker-compose.prod.yml \
  config >/tmp/myrss-prod-compose.yml

git status --short
```

Expected:

- Python tests pass.
- Ruff exits 0.
- Reader-web tests pass.
- Reader-web build passes.
- Compose config exits 0.
- `git status --short` contains only intended source/doc changes.

## Self-Review Checklist

- Core reading loop works before Agent UI polish.
- `read-later` and `starred` modules filter the correct article sets.
- Scoring DB outage does not prevent article reading.
- RSS HTML is sanitized before rendering.
- Generated files are not tracked.
- Reader-web has CI test/build coverage.
- Deployment wiring includes `READER_MINIFLUX_USER_ID`.
- The original long plan remains as historical context; this continuation plan is the execution guide for the next small iterations.

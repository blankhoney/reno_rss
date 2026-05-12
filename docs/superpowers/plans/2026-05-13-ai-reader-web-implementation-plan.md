# AI Reader Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new `reader-web` app that becomes the daily AI-assisted RSS reading interface while keeping Miniflux as the RSS backend.

**Architecture:** Add a Next.js full-stack service under `apps/reader-web` with server-side API routes. It reads article/feed/status data from Miniflux, reads AI scores and reader-only state from the scoring PostgreSQL database, and exposes a desktop-first reading workbench with a streaming current-article Agent. The existing `scorer-worker` is upgraded first so the frontend has stable multidimensional score data to consume.

**Tech Stack:** Next.js App Router, React, TypeScript, PostgreSQL (`pg`), Zod, Node test runner, Docker Compose, Caddy, Authelia, existing Python scorer-worker with pytest/ruff.

---

## Scope Check

The spec touches scoring, data API, frontend UI, reader state, feed management, Agent streaming, and deployment. These pieces are coupled by one user-facing feature: the AI reading workbench. This plan keeps them in one implementation plan but orders them as independently testable tasks. Do not start frontend UI work until the data contracts in Tasks 1-3 pass tests.

## File Structure

### Existing Python scorer-worker

- Modify `apps/scorer-worker/sql/001_init_scoring.sql`
  - Add `dimension_scores JSONB` to `item_scores`.
  - Add `reader_entry_states` for read-later and reader-specific state.
- Modify `apps/scorer-worker/src/scoring.py`
  - Parse LLM responses with `overall` plus seven dimensions.
  - Preserve legacy `score` as the overall score.
  - Preserve baseline fallback with a full dimension score object.
- Modify `apps/scorer-worker/src/repository.py`
  - Persist `dimension_scores`.
  - Add `upsert_reader_state()` and `get_reader_state()` only if needed by tests; reader-web will also manage this table directly.
- Modify tests under `apps/scorer-worker/tests/`
  - Verify multidimensional parsing, fallback dimensions, and DB writes.

### New Next.js reader-web app

- Create `apps/reader-web/package.json`
  - Defines app scripts and dependencies.
- Create `apps/reader-web/tsconfig.json`
  - TypeScript config for Next.js.
- Create `apps/reader-web/next.config.ts`
  - Minimal Next config.
- Create `apps/reader-web/Dockerfile`
  - Production container for Compose.
- Create `apps/reader-web/src/app/layout.tsx`
  - Root HTML shell.
- Create `apps/reader-web/src/app/page.tsx`
  - Main reading workbench.
- Create `apps/reader-web/src/app/globals.css`
  - Desktop-first layout styles and focus reading mode.
- Create `apps/reader-web/src/app/api/**/route.ts`
  - API route handlers for modules, articles, feeds, state actions, Agent streaming.
- Create `apps/reader-web/src/lib/config.ts`
  - Environment parsing.
- Create `apps/reader-web/src/lib/miniflux/client.ts`
  - Miniflux API client.
- Create `apps/reader-web/src/lib/scoring/db.ts`
  - PostgreSQL pool.
- Create `apps/reader-web/src/lib/scoring/repository.ts`
  - Score, state, and module queries.
- Create `apps/reader-web/src/lib/articles/service.ts`
  - Combines Miniflux article data with scores and reader state.
- Create `apps/reader-web/src/lib/agent/**`
  - Current-article Agent prompt, streaming, and web search client.
- Create `apps/reader-web/src/components/**`
  - Workbench, module sidebar, article list, article reader, score chips, Agent panel.
- Create `apps/reader-web/src/test/**`
  - Node test runner tests for data transforms, module sorting, Agent request building.

### Infra and docs

- Modify `.env.example`
  - Add reader-web and web-search variables.
- Modify `infra/compose/docker-compose.base.yml`
  - Add `reader-web` service.
- Modify `infra/compose/docker-compose.prod.yml`
  - Add prod app network alias.
- Modify `infra/compose/docker-compose.staging.yml`
  - Add staging app network alias.
- Create `infra/caddy/conf.d/reader-web.caddy`
  - Route `ai-reader` and `staging-ai-reader` through Authelia.
- Modify `docs/learning-notes.md`
  - Add learning notes after implementation tasks.

---

## Task 1: Upgrade scoring schema for multidimensional scores

**Files:**
- Modify: `apps/scorer-worker/sql/001_init_scoring.sql`
- Modify: `apps/scorer-worker/src/repository.py`
- Modify: `apps/scorer-worker/tests/test_repository.py`

- [ ] **Step 1: Write failing repository test for `dimension_scores` persistence**

Add this test to `apps/scorer-worker/tests/test_repository.py`:

```python
def test_upsert_score_persists_dimension_scores(db_conn):
    from repository import init_schema, upsert_score

    init_schema(db_conn)
    row = {
        "tenant_id": "default",
        "miniflux_entry_id": 123,
        "content_hash": "hash-123",
        "score": 86,
        "dimension_scores": {
            "importance": 90,
            "usefulness": 78,
            "timeliness": 84,
            "depth": 72,
            "technical_value": 92,
            "business_value": 48,
            "trend_value": 80,
        },
        "tags": ["ai", "agent"],
        "reason": "High technical value for an AI reader.",
        "model_version": "minimax:test:rss-score-v2",
        "model_provider": "minimax",
        "model_name": "test-model",
        "prompt_version": "rss-score-v2",
        "confidence": 0.91,
        "scoring_status": "success",
        "error_message": None,
    }

    upsert_score(db_conn, row)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT score, dimension_scores
            FROM item_scores
            WHERE tenant_id = %s AND miniflux_entry_id = %s
            """,
            ("default", 123),
        )
        score, dimension_scores = cur.fetchone()

    assert score == 86
    assert dimension_scores["technical_value"] == 92
    assert dimension_scores["business_value"] == 48
```

- [ ] **Step 2: Run repository test to verify it fails**

Run:

```bash
cd apps/scorer-worker
python -m pytest tests/test_repository.py::test_upsert_score_persists_dimension_scores -v
```

Expected: FAIL because `dimension_scores` is missing from the schema or insert query.

- [ ] **Step 3: Add `dimension_scores` to schema**

Modify `apps/scorer-worker/sql/001_init_scoring.sql` inside `item_scores`:

```sql
    score              INT         NOT NULL,
    dimension_scores   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    tags               JSONB       NOT NULL,
```

Add this idempotent migration after the `CREATE TABLE IF NOT EXISTS item_scores` block:

```sql
ALTER TABLE item_scores
    ADD COLUMN IF NOT EXISTS dimension_scores JSONB NOT NULL DEFAULT '{}'::jsonb;
```

- [ ] **Step 4: Persist `dimension_scores` in repository**

Modify `apps/scorer-worker/src/repository.py` in `upsert_score()`:

```python
    if isinstance(serialized.get("tags"), list):
        serialized["tags"] = json.dumps(serialized["tags"])
    if isinstance(serialized.get("dimension_scores"), dict):
        serialized["dimension_scores"] = json.dumps(serialized["dimension_scores"])
    if not serialized.get("dimension_scores"):
        serialized["dimension_scores"] = json.dumps({})
```

Update the SQL insert:

```sql
            INSERT INTO item_scores (
                tenant_id, miniflux_entry_id, content_hash,
                score, dimension_scores, tags, reason, model_version,
                model_provider, model_name, prompt_version,
                confidence, scoring_status, error_message
            ) VALUES (
                %(tenant_id)s, %(miniflux_entry_id)s, %(content_hash)s,
                %(score)s, %(dimension_scores)s::jsonb, %(tags)s::jsonb, %(reason)s, %(model_version)s,
                %(model_provider)s, %(model_name)s, %(prompt_version)s,
                %(confidence)s, %(scoring_status)s, %(error_message)s
            )
            ON CONFLICT (tenant_id, miniflux_entry_id, content_hash, model_version)
            DO UPDATE SET
                score            = EXCLUDED.score,
                dimension_scores = EXCLUDED.dimension_scores,
                tags             = EXCLUDED.tags,
                reason           = EXCLUDED.reason,
                confidence       = EXCLUDED.confidence,
                scoring_status   = EXCLUDED.scoring_status,
                error_message    = EXCLUDED.error_message,
                scored_at        = NOW();
```

- [ ] **Step 5: Run repository tests**

Run:

```bash
cd apps/scorer-worker
python -m pytest tests/test_repository.py -v
python -m ruff check src tests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/scorer-worker/sql/001_init_scoring.sql apps/scorer-worker/src/repository.py apps/scorer-worker/tests/test_repository.py
git commit -m "feat(scorer-worker): persist multidimensional scores"
```

---

## Task 2: Upgrade scoring parser and prompt to produce dimensions

**Files:**
- Modify: `apps/scorer-worker/src/scoring.py`
- Modify: `apps/scorer-worker/tests/test_scoring.py`

- [ ] **Step 1: Write failing test for successful multidimensional LLM output**

Add to `apps/scorer-worker/tests/test_scoring.py`:

```python
class FakeLLMClient:
    model = "test-model"

    def chat_completion(self, messages):
        return """
        {
          "overall": 86,
          "importance": 90,
          "usefulness": 78,
          "timeliness": 84,
          "depth": 72,
          "technical_value": 92,
          "business_value": 48,
          "trend_value": 80,
          "tags": ["AI", "Agent", "Engineering", "Extra"],
          "reason": "Useful for building an AI assisted RSS reader.",
          "confidence": 0.91
        }
        """


def test_score_entry_returns_dimension_scores_from_llm():
    payload = score_entry(
        {"id": 1, "title": "Agent reading", "content": "Long article about AI agents."},
        llm_client=FakeLLMClient(),
    )

    assert payload["score"] == 86
    assert payload["dimension_scores"] == {
        "importance": 90,
        "usefulness": 78,
        "timeliness": 84,
        "depth": 72,
        "technical_value": 92,
        "business_value": 48,
        "trend_value": 80,
    }
    assert payload["tags"] == ["ai", "agent", "engineering"]
    assert payload["prompt_version"] == "rss-score-v2"
```

- [ ] **Step 2: Write failing test for fallback dimensions**

Add:

```python
class BrokenLLMClient:
    model = "broken-model"

    def chat_completion(self, messages):
        raise RuntimeError("provider unavailable")


def test_score_entry_fallback_includes_dimension_scores():
    payload = score_entry(
        {"id": 1, "title": "Fallback", "content": "x" * 500},
        llm_client=BrokenLLMClient(),
    )

    assert payload["scoring_status"] == "error"
    assert payload["score"] == 10
    assert payload["dimension_scores"]["importance"] == 10
    assert payload["dimension_scores"]["technical_value"] == 10
    assert payload["dimension_scores"]["business_value"] == 10
```

- [ ] **Step 3: Run scoring tests to verify they fail**

Run:

```bash
cd apps/scorer-worker
python -m pytest tests/test_scoring.py -v
```

Expected: FAIL because `dimension_scores` and prompt version `rss-score-v2` are not implemented.

- [ ] **Step 4: Define dimension keys and prompt version**

Modify top constants in `apps/scorer-worker/src/scoring.py`:

```python
_PROMPT_VERSION = "rss-score-v2"
_DIMENSION_KEYS = (
    "importance",
    "usefulness",
    "timeliness",
    "depth",
    "technical_value",
    "business_value",
    "trend_value",
)
```

- [ ] **Step 5: Update successful payload**

Modify the return value in `score_entry()`:

```python
    return {
        "score": result["score"],
        "dimension_scores": result["dimension_scores"],
        "tags": result["tags"],
        "reason": result["reason"],
        "model_version": f"{_LLM_MODEL_PROVIDER}:{model_name}:{_PROMPT_VERSION}",
        "model_provider": _LLM_MODEL_PROVIDER,
        "model_name": model_name,
        "prompt_version": _PROMPT_VERSION,
        "confidence": result["confidence"],
        "scoring_status": "success",
        "error_message": None,
    }
```

- [ ] **Step 6: Update fallback payload**

Modify `_baseline_payload()`:

```python
    dimension_scores = {key: raw_score for key in _DIMENSION_KEYS}

    return {
        "score": raw_score,
        "dimension_scores": dimension_scores,
        "tags": tags,
        "reason": _trim_reason(f"length={len(combined)} hash={content_hash}"),
        "model_version": _MODEL_VERSION,
        "model_provider": _MODEL_PROVIDER,
        "model_name": _MODEL_NAME,
        "prompt_version": _PROMPT_VERSION,
        "confidence": round(min(1.0, len(combined) / 500), 3),
        "scoring_status": "error" if error_message else "success",
        "error_message": error_message,
    }
```

- [ ] **Step 7: Update prompt to request strict multidimensional JSON**

Replace `_build_messages()` system content:

```python
                "You score RSS entries for a personal AI reading workspace. "
                "Return strict JSON only with keys: overall, importance, usefulness, "
                "timeliness, depth, technical_value, business_value, trend_value, "
                "tags, reason, confidence. All score fields must be integers from 0 to 100. "
                "tags must be short strings. confidence must be 0.0 to 1.0. "
                "Do not include markdown, comments, or any text outside the JSON object."
```

- [ ] **Step 8: Parse multidimensional JSON**

Replace `_parse_llm_json()`:

```python
def _parse_llm_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid llm json") from exc

    score = _clamp_int(data.get("overall", data.get("score")), minimum=0, maximum=100)
    dimension_scores = {
        key: _clamp_int(data.get(key), minimum=0, maximum=100)
        for key in _DIMENSION_KEYS
    }
    tags = _normalize_tags(data.get("tags"))
    reason = _trim_reason(str(data.get("reason") or "No reason provided."))
    confidence = _clamp_float(data.get("confidence"), minimum=0.0, maximum=1.0)
    return {
        "score": score,
        "dimension_scores": dimension_scores,
        "tags": tags,
        "reason": reason,
        "confidence": confidence,
    }
```

- [ ] **Step 9: Run scorer tests**

Run:

```bash
cd apps/scorer-worker
python -m pytest tests/test_scoring.py tests/test_main_flow.py -v
python -m ruff check src tests
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add apps/scorer-worker/src/scoring.py apps/scorer-worker/tests/test_scoring.py
git commit -m "feat(scorer-worker): score RSS entries across dimensions"
```

---

## Task 3: Add reader state table and repository contract

**Files:**
- Modify: `apps/scorer-worker/sql/001_init_scoring.sql`
- Create: `apps/reader-web/src/lib/scoring/schema.sql`
- Create: `apps/reader-web/src/lib/scoring/repository.ts`
- Create: `apps/reader-web/src/lib/scoring/repository.test.ts`

- [ ] **Step 1: Add `reader_entry_states` to scoring schema**

Append to `apps/scorer-worker/sql/001_init_scoring.sql`:

```sql
CREATE TABLE IF NOT EXISTS reader_entry_states (
    tenant_id          TEXT        NOT NULL,
    miniflux_user_id   BIGINT      NOT NULL,
    miniflux_entry_id  BIGINT      NOT NULL,
    read_later         BOOLEAN     NOT NULL DEFAULT FALSE,
    last_read_at       TIMESTAMPTZ,
    archived_at        TIMESTAMPTZ,
    notes              TEXT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, miniflux_user_id, miniflux_entry_id)
);
```

- [ ] **Step 2: Create reader-web scoring SQL copy**

Create `apps/reader-web/src/lib/scoring/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS reader_entry_states (
    tenant_id          TEXT        NOT NULL,
    miniflux_user_id   BIGINT      NOT NULL,
    miniflux_entry_id  BIGINT      NOT NULL,
    read_later         BOOLEAN     NOT NULL DEFAULT FALSE,
    last_read_at       TIMESTAMPTZ,
    archived_at        TIMESTAMPTZ,
    notes              TEXT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, miniflux_user_id, miniflux_entry_id)
);
```

- [ ] **Step 3: Scaffold minimal Node test setup if reader-web does not exist yet**

If `apps/reader-web/package.json` does not exist, create it now:

```json
{
  "name": "reader-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "test": "node --test --import tsx 'src/**/*.test.ts'",
    "lint": "next lint"
  },
  "dependencies": {
    "@types/pg": "latest",
    "next": "latest",
    "pg": "latest",
    "react": "latest",
    "react-dom": "latest",
    "zod": "latest"
  },
  "devDependencies": {
    "@types/node": "latest",
    "@types/react": "latest",
    "@types/react-dom": "latest",
    "tsx": "latest",
    "typescript": "latest"
  }
}
```

Run:

```bash
cd apps/reader-web
npm install
```

Expected: `package-lock.json` is created.

- [ ] **Step 4: Write failing repository unit test with a fake query client**

Create `apps/reader-web/src/lib/scoring/repository.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { setReadLaterSql, toArticleScore } from "./repository";

test("setReadLaterSql builds an idempotent upsert", () => {
  const query = setReadLaterSql({
    tenantId: "default",
    minifluxUserId: 7,
    minifluxEntryId: 42,
    readLater: true,
  });

  assert.equal(query.values[0], "default");
  assert.equal(query.values[1], 7);
  assert.equal(query.values[2], 42);
  assert.equal(query.values[3], true);
  assert.match(query.text, /ON CONFLICT/);
  assert.match(query.text, /read_later\s*=\s*EXCLUDED\.read_later/);
});

test("toArticleScore normalizes legacy rows without dimension_scores", () => {
  const score = toArticleScore({
    score: 71,
    dimension_scores: null,
    tags: ["ai"],
    reason: "legacy",
    scored_at: "2026-05-13T00:00:00.000Z",
  });

  assert.equal(score.overall, 71);
  assert.equal(score.dimensions.technical_value, 71);
  assert.deepEqual(score.tags, ["ai"]);
});
```

- [ ] **Step 5: Run test to verify it fails**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/scoring/repository.test.ts
```

Expected: FAIL because `repository.ts` does not exist.

- [ ] **Step 6: Implement scoring repository helpers**

Create `apps/reader-web/src/lib/scoring/repository.ts`:

```ts
export type DimensionKey =
  | "importance"
  | "usefulness"
  | "timeliness"
  | "depth"
  | "technical_value"
  | "business_value"
  | "trend_value";

export type ArticleScore = {
  overall: number;
  dimensions: Record<DimensionKey, number>;
  tags: string[];
  reason: string;
  scoredAt: string | null;
};

const dimensionKeys: DimensionKey[] = [
  "importance",
  "usefulness",
  "timeliness",
  "depth",
  "technical_value",
  "business_value",
  "trend_value",
];

type ScoreRow = {
  score: number;
  dimension_scores: Partial<Record<DimensionKey, number>> | null;
  tags: string[] | string | null;
  reason: string | null;
  scored_at: string | Date | null;
};

export function toArticleScore(row: ScoreRow): ArticleScore {
  const overall = clampScore(row.score);
  const source = row.dimension_scores ?? {};
  const dimensions = Object.fromEntries(
    dimensionKeys.map((key) => [key, clampScore(source[key] ?? overall)]),
  ) as Record<DimensionKey, number>;

  return {
    overall,
    dimensions,
    tags: normalizeTags(row.tags),
    reason: row.reason ?? "",
    scoredAt: row.scored_at ? new Date(row.scored_at).toISOString() : null,
  };
}

export function setReadLaterSql(input: {
  tenantId: string;
  minifluxUserId: number;
  minifluxEntryId: number;
  readLater: boolean;
}) {
  return {
    text: `
      INSERT INTO reader_entry_states (
        tenant_id, miniflux_user_id, miniflux_entry_id, read_later, updated_at
      )
      VALUES ($1, $2, $3, $4, NOW())
      ON CONFLICT (tenant_id, miniflux_user_id, miniflux_entry_id)
      DO UPDATE SET
        read_later = EXCLUDED.read_later,
        updated_at = NOW()
    `,
    values: [
      input.tenantId,
      input.minifluxUserId,
      input.minifluxEntryId,
      input.readLater,
    ],
  };
}

function clampScore(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function normalizeTags(value: ScoreRow["tags"]): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return [];
    }
  }
  return [];
}
```

- [ ] **Step 7: Run tests**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/scoring/repository.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/scorer-worker/sql/001_init_scoring.sql apps/reader-web/package.json apps/reader-web/package-lock.json apps/reader-web/src/lib/scoring/schema.sql apps/reader-web/src/lib/scoring/repository.ts apps/reader-web/src/lib/scoring/repository.test.ts
git commit -m "feat(reader-web): add reader state data contract"
```

---

## Task 4: Scaffold reader-web app shell and Docker image

**Files:**
- Create/Modify: `apps/reader-web/package.json`
- Create: `apps/reader-web/tsconfig.json`
- Create: `apps/reader-web/next.config.ts`
- Create: `apps/reader-web/src/app/layout.tsx`
- Create: `apps/reader-web/src/app/page.tsx`
- Create: `apps/reader-web/src/app/globals.css`
- Create: `apps/reader-web/Dockerfile`

- [ ] **Step 1: Create TypeScript and Next config**

Create `apps/reader-web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "es2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

Create `apps/reader-web/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

- [ ] **Step 2: Create root layout**

Create `apps/reader-web/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Reader",
  description: "AI-assisted RSS reading workspace",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 3: Create initial page**

Create `apps/reader-web/src/app/page.tsx`:

```tsx
export default function HomePage() {
  return (
    <main className="shell">
      <aside className="sidebar">
        <strong>AI Reader</strong>
        <nav>
          <a href="#unread">未读</a>
          <a href="#saved">收藏</a>
          <a href="#later">稍后读</a>
        </nav>
      </aside>
      <section className="listPane">
        <h1>阅读工作台</h1>
        <p>文章列表会在 API 接通后显示在这里。</p>
      </section>
      <article className="readerPane">
        <h2>站内阅读</h2>
        <p>选择文章后，这里展示正文、分数和当前文章 Agent。</p>
      </article>
    </main>
  );
}
```

- [ ] **Step 4: Create desktop-first CSS**

Create `apps/reader-web/src/app/globals.css`:

```css
:root {
  color-scheme: light;
  --border: #e5e7eb;
  --muted: #6b7280;
  --bg: #f8fafc;
  --panel: #ffffff;
  --text: #111827;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

a {
  color: inherit;
  text-decoration: none;
}

.shell {
  display: grid;
  grid-template-columns: 220px minmax(320px, 420px) minmax(0, 1fr);
  min-height: 100vh;
}

.sidebar,
.listPane,
.readerPane {
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 20px;
}

.sidebar nav {
  display: grid;
  gap: 10px;
  margin-top: 24px;
}

.listPane p,
.readerPane p {
  color: var(--muted);
}

@media (max-width: 900px) {
  .shell {
    grid-template-columns: 1fr;
  }

  .sidebar,
  .listPane,
  .readerPane {
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }
}
```

- [ ] **Step 5: Create Dockerfile**

Create `apps/reader-web/Dockerfile`:

```Dockerfile
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 6: Build locally**

Run:

```bash
cd apps/reader-web
npm run build
```

Expected: Next.js production build succeeds.

- [ ] **Step 7: Commit**

```bash
git add apps/reader-web
git commit -m "feat(reader-web): scaffold AI reader app shell"
```

---

## Task 5: Implement Miniflux client and article normalization

**Files:**
- Create: `apps/reader-web/src/lib/config.ts`
- Create: `apps/reader-web/src/lib/miniflux/client.ts`
- Create: `apps/reader-web/src/lib/miniflux/client.test.ts`
- Create: `apps/reader-web/src/lib/articles/types.ts`

- [ ] **Step 1: Write failing test for Miniflux URL construction**

Create `apps/reader-web/src/lib/miniflux/client.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { buildEntriesUrl, normalizeMinifluxEntry } from "./client";

test("buildEntriesUrl includes status, order and pagination", () => {
  const url = buildEntriesUrl("http://miniflux:8080", {
    status: "unread",
    limit: 50,
    offset: 10,
  });

  assert.equal(
    url.toString(),
    "http://miniflux:8080/v1/entries?status=unread&limit=50&offset=10&order=published_at&direction=desc",
  );
});

test("normalizeMinifluxEntry preserves reading fields", () => {
  const entry = normalizeMinifluxEntry({
    id: 42,
    user_id: 7,
    feed_id: 9,
    title: "Example",
    url: "https://example.com/post",
    content: "<p>Hello</p>",
    status: "unread",
    starred: false,
    published_at: "2026-05-13T00:00:00Z",
    feed: {
      id: 9,
      title: "Feed",
      category: { id: 3, title: "AI" },
    },
  });

  assert.equal(entry.id, 42);
  assert.equal(entry.userId, 7);
  assert.equal(entry.feedTitle, "Feed");
  assert.equal(entry.categoryTitle, "AI");
  assert.equal(entry.status, "unread");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/miniflux/client.test.ts
```

Expected: FAIL because client module does not exist.

- [ ] **Step 3: Implement shared article types**

Create `apps/reader-web/src/lib/articles/types.ts`:

```ts
import type { ArticleScore } from "@/lib/scoring/repository";

export type ArticleStatus = "read" | "unread" | "removed";

export type Article = {
  id: number;
  userId: number;
  feedId: number | null;
  feedTitle: string;
  categoryId: number | null;
  categoryTitle: string;
  title: string;
  url: string;
  contentHtml: string;
  status: ArticleStatus;
  starred: boolean;
  publishedAt: string | null;
  score: ArticleScore | null;
  readLater: boolean;
  lastReadAt: string | null;
};
```

- [ ] **Step 4: Implement config parser**

Create `apps/reader-web/src/lib/config.ts`:

```ts
import { z } from "zod";

const envSchema = z.object({
  MINIFLUX_API_BASE_URL: z.string().url(),
  MINIFLUX_USERNAME: z.string().min(1),
  MINIFLUX_PASSWORD: z.string().min(1),
  SCORING_DATABASE_URL: z.string().min(1),
  READER_TENANT_ID: z.string().default("default"),
  MINIMAX_API_KEY: z.string().optional(),
  MINIMAX_BASE_URL: z.string().url().optional(),
  MINIMAX_MODEL: z.string().optional(),
  WEB_SEARCH_PROVIDER: z.enum(["none", "brave"]).default("none"),
  WEB_SEARCH_API_KEY: z.string().optional(),
});

export function getConfig() {
  return envSchema.parse(process.env);
}
```

- [ ] **Step 5: Implement Miniflux client helpers**

Create `apps/reader-web/src/lib/miniflux/client.ts`:

```ts
import type { ArticleStatus } from "@/lib/articles/types";

type EntryFilter = {
  status?: ArticleStatus | "all";
  limit?: number;
  offset?: number;
  categoryId?: number;
  starred?: boolean;
};

export type MinifluxEntry = {
  id: number;
  user_id: number;
  feed_id?: number;
  title?: string;
  url?: string;
  content?: string;
  status?: ArticleStatus;
  starred?: boolean;
  published_at?: string;
  feed?: {
    id?: number;
    title?: string;
    category?: {
      id?: number;
      title?: string;
    };
  };
};

export function buildEntriesUrl(baseUrl: string, filter: EntryFilter): URL {
  const url = new URL("/v1/entries", baseUrl.replace(/\/$/, ""));
  if (filter.status && filter.status !== "all") url.searchParams.set("status", filter.status);
  if (filter.starred !== undefined) url.searchParams.set("starred", String(filter.starred));
  if (filter.categoryId !== undefined) url.searchParams.set("category_id", String(filter.categoryId));
  url.searchParams.set("limit", String(filter.limit ?? 50));
  url.searchParams.set("offset", String(filter.offset ?? 0));
  url.searchParams.set("order", "published_at");
  url.searchParams.set("direction", "desc");
  return url;
}

export function normalizeMinifluxEntry(entry: MinifluxEntry) {
  return {
    id: entry.id,
    userId: entry.user_id,
    feedId: entry.feed_id ?? entry.feed?.id ?? null,
    feedTitle: entry.feed?.title ?? "",
    categoryId: entry.feed?.category?.id ?? null,
    categoryTitle: entry.feed?.category?.title ?? "未分类",
    title: entry.title ?? "",
    url: entry.url ?? "",
    contentHtml: entry.content ?? "",
    status: entry.status ?? "unread",
    starred: Boolean(entry.starred),
    publishedAt: entry.published_at ?? null,
  };
}

export class MinifluxClient {
  constructor(
    private readonly baseUrl: string,
    private readonly username: string,
    private readonly password: string,
  ) {}

  async getEntries(filter: EntryFilter): Promise<ReturnType<typeof normalizeMinifluxEntry>[]> {
    const response = await fetch(buildEntriesUrl(this.baseUrl, filter), {
      headers: {
        Authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString("base64")}`,
      },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Miniflux entries request failed: ${response.status}`);
    }
    const data = (await response.json()) as { entries?: MinifluxEntry[] };
    return (data.entries ?? []).map(normalizeMinifluxEntry);
  }
}
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/miniflux/client.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/reader-web/src/lib/config.ts apps/reader-web/src/lib/miniflux apps/reader-web/src/lib/articles
git commit -m "feat(reader-web): add Miniflux article client"
```

---

## Task 6: Implement modules and article API

**Files:**
- Create: `apps/reader-web/src/lib/articles/service.ts`
- Create: `apps/reader-web/src/lib/articles/service.test.ts`
- Create: `apps/reader-web/src/app/api/modules/route.ts`
- Create: `apps/reader-web/src/app/api/articles/route.ts`
- Create: `apps/reader-web/src/app/api/articles/[id]/route.ts`

- [ ] **Step 1: Write failing module sorting test**

Create `apps/reader-web/src/lib/articles/service.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { sortArticlesForModule } from "./service";
import type { Article } from "./types";

function article(id: number, technical: number, business: number): Article {
  return {
    id,
    userId: 1,
    feedId: 1,
    feedTitle: "Feed",
    categoryId: 1,
    categoryTitle: "AI",
    title: `Article ${id}`,
    url: "https://example.com",
    contentHtml: "<p>Body</p>",
    status: "unread",
    starred: false,
    publishedAt: "2026-05-13T00:00:00Z",
    readLater: false,
    lastReadAt: null,
    score: {
      overall: 70,
      dimensions: {
        importance: 70,
        usefulness: 70,
        timeliness: 70,
        depth: 70,
        technical_value: technical,
        business_value: business,
        trend_value: 70,
      },
      tags: ["ai"],
      reason: "reason",
      scoredAt: null,
    },
  };
}

test("technical module sorts by technical_value descending", () => {
  const sorted = sortArticlesForModule([article(1, 40, 90), article(2, 95, 10)], "technical");
  assert.deepEqual(sorted.map((item) => item.id), [2, 1]);
});

test("business module sorts by business_value descending", () => {
  const sorted = sortArticlesForModule([article(1, 40, 90), article(2, 95, 10)], "business");
  assert.deepEqual(sorted.map((item) => item.id), [1, 2]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/articles/service.test.ts
```

Expected: FAIL because `service.ts` does not exist.

- [ ] **Step 3: Implement article sorting service**

Create `apps/reader-web/src/lib/articles/service.ts`:

```ts
import type { Article } from "./types";

export type ModuleId =
  | "unread"
  | "read"
  | "starred"
  | "read-later"
  | "technical"
  | "business"
  | "trend"
  | "ai"
  | "product"
  | "security";

export function sortArticlesForModule(articles: Article[], moduleId: ModuleId): Article[] {
  return [...articles].sort((a, b) => scoreForModule(b, moduleId) - scoreForModule(a, moduleId));
}

export function scoreForModule(article: Article, moduleId: ModuleId): number {
  const score = article.score;
  if (!score) return 0;
  switch (moduleId) {
    case "technical":
      return score.dimensions.technical_value;
    case "business":
      return score.dimensions.business_value;
    case "trend":
      return Math.round((score.dimensions.trend_value + score.dimensions.timeliness) / 2);
    case "product":
      return Math.round((score.dimensions.usefulness + score.dimensions.business_value) / 2);
    case "security":
      return Math.round((score.dimensions.importance + score.dimensions.technical_value) / 2);
    default:
      return score.overall;
  }
}
```

- [ ] **Step 4: Create modules API route**

Create `apps/reader-web/src/app/api/modules/route.ts`:

```ts
import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    modules: [
      { id: "unread", title: "未读", defaultSort: "overall" },
      { id: "read", title: "已读", defaultSort: "last_read_at" },
      { id: "starred", title: "收藏", defaultSort: "overall" },
      { id: "read-later", title: "稍后读", defaultSort: "overall" },
      { id: "technical", title: "技术", defaultSort: "technical_value" },
      { id: "business", title: "商业", defaultSort: "business_value" },
      { id: "trend", title: "趋势", defaultSort: "trend_value" },
      { id: "ai", title: "AI", defaultSort: "technical_value" },
      { id: "product", title: "产品", defaultSort: "usefulness" },
      { id: "security", title: "安全", defaultSort: "importance" },
    ],
  });
}
```

- [ ] **Step 5: Create explicit 501 article API routes before data wiring**

Create `apps/reader-web/src/app/api/articles/route.ts`:

```ts
import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json(
    { error: "Article list data source is not connected yet" },
    { status: 501 },
  );
}
```

Create `apps/reader-web/src/app/api/articles/[id]/route.ts`:

```ts
import { NextResponse } from "next/server";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return NextResponse.json(
    { error: "Article detail data source is not connected yet", id },
    { status: 501 },
  );
}
```

- [ ] **Step 6: Run tests and build**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/articles/service.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/reader-web/src/lib/articles apps/reader-web/src/app/api
git commit -m "feat(reader-web): add article modules contract"
```

---

## Task 7: Connect article API to Miniflux and scoring DB

**Files:**
- Create: `apps/reader-web/src/lib/scoring/db.ts`
- Modify: `apps/reader-web/src/lib/scoring/repository.ts`
- Modify: `apps/reader-web/src/lib/articles/service.ts`
- Modify: `apps/reader-web/src/app/api/articles/route.ts`
- Modify: `apps/reader-web/src/app/api/articles/[id]/route.ts`

- [ ] **Step 1: Add PostgreSQL pool**

Create `apps/reader-web/src/lib/scoring/db.ts`:

```ts
import { Pool } from "pg";
import { getConfig } from "@/lib/config";

let pool: Pool | undefined;

export function getPool() {
  if (!pool) {
    pool = new Pool({
      connectionString: getConfig().SCORING_DATABASE_URL,
      max: 5,
    });
  }
  return pool;
}
```

- [ ] **Step 2: Add score query helper**

Append to `apps/reader-web/src/lib/scoring/repository.ts`:

```ts
import type { Pool } from "pg";

export async function getScoresByEntryIds(
  pool: Pool,
  tenantId: string,
  entryIds: number[],
): Promise<Map<number, ArticleScore>> {
  if (entryIds.length === 0) return new Map();
  const result = await pool.query(
    `
      SELECT DISTINCT ON (miniflux_entry_id)
        miniflux_entry_id, score, dimension_scores, tags, reason, scored_at
      FROM item_scores
      WHERE tenant_id = $1
        AND miniflux_entry_id = ANY($2::bigint[])
      ORDER BY miniflux_entry_id, scored_at DESC
    `,
    [tenantId, entryIds],
  );
  return new Map(
    result.rows.map((row) => [Number(row.miniflux_entry_id), toArticleScore(row)]),
  );
}

export async function getReaderStatesByEntryIds(
  pool: Pool,
  tenantId: string,
  minifluxUserId: number,
  entryIds: number[],
): Promise<Map<number, { readLater: boolean; lastReadAt: string | null }>> {
  if (entryIds.length === 0) return new Map();
  const result = await pool.query(
    `
      SELECT miniflux_entry_id, read_later, last_read_at
      FROM reader_entry_states
      WHERE tenant_id = $1
        AND miniflux_user_id = $2
        AND miniflux_entry_id = ANY($3::bigint[])
    `,
    [tenantId, minifluxUserId, entryIds],
  );
  return new Map(
    result.rows.map((row) => [
      Number(row.miniflux_entry_id),
      {
        readLater: Boolean(row.read_later),
        lastReadAt: row.last_read_at ? new Date(row.last_read_at).toISOString() : null,
      },
    ]),
  );
}
```

- [ ] **Step 3: Add article merge helper**

Append to `apps/reader-web/src/lib/articles/service.ts`:

```ts
import type { Article } from "./types";
import type { ArticleScore } from "@/lib/scoring/repository";

type MinifluxArticle = Omit<Article, "score" | "readLater" | "lastReadAt">;

export function mergeArticleData(
  articles: MinifluxArticle[],
  scores: Map<number, ArticleScore>,
  states: Map<number, { readLater: boolean; lastReadAt: string | null }>,
): Article[] {
  return articles.map((article) => {
    const state = states.get(article.id);
    return {
      ...article,
      score: scores.get(article.id) ?? null,
      readLater: state?.readLater ?? false,
      lastReadAt: state?.lastReadAt ?? null,
    };
  });
}
```

- [ ] **Step 4: Connect article list route**

Replace `apps/reader-web/src/app/api/articles/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getConfig } from "@/lib/config";
import { MinifluxClient } from "@/lib/miniflux/client";
import { getPool } from "@/lib/scoring/db";
import { getReaderStatesByEntryIds, getScoresByEntryIds } from "@/lib/scoring/repository";
import { mergeArticleData, sortArticlesForModule, type ModuleId } from "@/lib/articles/service";

export async function GET(request: Request) {
  const config = getConfig();
  const url = new URL(request.url);
  const moduleId = (url.searchParams.get("module") ?? "unread") as ModuleId;
  const limit = Number(url.searchParams.get("limit") ?? 50);
  const status = moduleId === "read" ? "read" : "unread";
  const starred = moduleId === "starred" ? true : undefined;

  const miniflux = new MinifluxClient(
    config.MINIFLUX_API_BASE_URL,
    config.MINIFLUX_USERNAME,
    config.MINIFLUX_PASSWORD,
  );
  const baseArticles = await miniflux.getEntries({ status, starred, limit });
  const entryIds = baseArticles.map((article) => article.id);
  const minifluxUserId = baseArticles[0]?.userId ?? 0;
  const pool = getPool();
  const [scores, states] = await Promise.all([
    getScoresByEntryIds(pool, config.READER_TENANT_ID, entryIds),
    getReaderStatesByEntryIds(pool, config.READER_TENANT_ID, minifluxUserId, entryIds),
  ]);
  const articles = sortArticlesForModule(
    mergeArticleData(baseArticles, scores, states),
    moduleId,
  );

  return NextResponse.json({ articles });
}
```

- [ ] **Step 5: Build**

Run:

```bash
cd apps/reader-web
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/reader-web/src/lib apps/reader-web/src/app/api/articles
git commit -m "feat(reader-web): connect article API to RSS and scores"
```

---

## Task 8: Build desktop reading workbench UI

**Files:**
- Create: `apps/reader-web/src/components/ModuleSidebar.tsx`
- Create: `apps/reader-web/src/components/ArticleList.tsx`
- Create: `apps/reader-web/src/components/ArticleReader.tsx`
- Create: `apps/reader-web/src/components/ScoreBadge.tsx`
- Modify: `apps/reader-web/src/app/page.tsx`
- Modify: `apps/reader-web/src/app/globals.css`

- [ ] **Step 1: Create score badge component**

Create `apps/reader-web/src/components/ScoreBadge.tsx`:

```tsx
export function ScoreBadge({ label, value }: { label: string; value: number | null }) {
  const display = value === null ? "--" : String(value);
  return (
    <span className="scoreBadge" title={label}>
      <span>{label}</span>
      <strong>{display}</strong>
    </span>
  );
}
```

- [ ] **Step 2: Create module sidebar**

Create `apps/reader-web/src/components/ModuleSidebar.tsx`:

```tsx
const modules = [
  ["unread", "未读"],
  ["read", "已读"],
  ["starred", "收藏"],
  ["read-later", "稍后读"],
  ["technical", "技术"],
  ["business", "商业"],
  ["trend", "趋势"],
  ["ai", "AI"],
  ["product", "产品"],
  ["security", "安全"],
  ["feeds", "订阅源管理"],
] as const;

export function ModuleSidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">AI Reader</div>
      <nav className="moduleNav">
        {modules.map(([id, title]) => (
          <a href={`?module=${id}`} key={id}>
            {title}
          </a>
        ))}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 3: Create article list**

Create `apps/reader-web/src/components/ArticleList.tsx`:

```tsx
import type { Article } from "@/lib/articles/types";
import { ScoreBadge } from "./ScoreBadge";

export function ArticleList({ articles }: { articles: Article[] }) {
  return (
    <section className="listPane">
      <div className="paneHeader">
        <h1>文章</h1>
        <select aria-label="排序维度" defaultValue="default">
          <option value="default">模块默认排序</option>
          <option value="overall">综合分</option>
          <option value="technical_value">技术价值</option>
          <option value="business_value">商业价值</option>
          <option value="trend_value">趋势价值</option>
          <option value="depth">深度</option>
        </select>
      </div>
      <div className="articleList">
        {articles.map((article) => (
          <a className="articleCard" href={`?article=${article.id}`} key={article.id}>
            <div className="articleMeta">{article.feedTitle} · {article.categoryTitle}</div>
            <h2>{article.title}</h2>
            <div className="scoreRow">
              <ScoreBadge label="综合" value={article.score?.overall ?? null} />
              <ScoreBadge label="技术" value={article.score?.dimensions.technical_value ?? null} />
              <ScoreBadge label="商业" value={article.score?.dimensions.business_value ?? null} />
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Create article reader**

Create `apps/reader-web/src/components/ArticleReader.tsx`:

```tsx
import type { Article } from "@/lib/articles/types";
import { ScoreBadge } from "./ScoreBadge";

export function ArticleReader({ article }: { article: Article | null }) {
  if (!article) {
    return (
      <article className="readerPane">
        <h2>选择一篇文章</h2>
        <p>正文、分数、评分理由和 Agent 会显示在这里。</p>
      </article>
    );
  }

  return (
    <article className="readerPane">
      <div className="readerToolbar">
        <a href={article.url} target="_blank" rel="noreferrer">打开原文</a>
        <button type="button">专注阅读</button>
        <button type="button">收藏</button>
        <button type="button">稍后读</button>
      </div>
      <h1>{article.title}</h1>
      <div className="scoreGrid">
        <ScoreBadge label="综合" value={article.score?.overall ?? null} />
        <ScoreBadge label="重要" value={article.score?.dimensions.importance ?? null} />
        <ScoreBadge label="实用" value={article.score?.dimensions.usefulness ?? null} />
        <ScoreBadge label="时效" value={article.score?.dimensions.timeliness ?? null} />
        <ScoreBadge label="深度" value={article.score?.dimensions.depth ?? null} />
        <ScoreBadge label="技术" value={article.score?.dimensions.technical_value ?? null} />
        <ScoreBadge label="商业" value={article.score?.dimensions.business_value ?? null} />
        <ScoreBadge label="趋势" value={article.score?.dimensions.trend_value ?? null} />
      </div>
      {article.score?.reason ? <p className="reason">{article.score.reason}</p> : null}
      <div className="content" dangerouslySetInnerHTML={{ __html: article.contentHtml }} />
    </article>
  );
}
```

- [ ] **Step 5: Wire page with server-side fetch fallback**

Replace `apps/reader-web/src/app/page.tsx`:

```tsx
import { ArticleList } from "@/components/ArticleList";
import { ArticleReader } from "@/components/ArticleReader";
import { ModuleSidebar } from "@/components/ModuleSidebar";
import type { Article } from "@/lib/articles/types";

async function getArticles(): Promise<Article[]> {
  try {
    const response = await fetch("http://localhost:3000/api/articles?module=unread", {
      cache: "no-store",
    });
    if (!response.ok) return [];
    const data = (await response.json()) as { articles?: Article[] };
    return data.articles ?? [];
  } catch {
    return [];
  }
}

export default async function HomePage() {
  const articles = await getArticles();
  return (
    <main className="shell">
      <ModuleSidebar />
      <ArticleList articles={articles} />
      <ArticleReader article={articles[0] ?? null} />
    </main>
  );
}
```

- [ ] **Step 6: Extend CSS for cards and reader**

Append to `apps/reader-web/src/app/globals.css`:

```css
.brand {
  font-size: 18px;
  font-weight: 800;
}

.moduleNav {
  display: grid;
  gap: 8px;
  margin-top: 24px;
}

.moduleNav a,
.articleCard,
.readerToolbar button,
.readerToolbar a {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
  padding: 10px 12px;
}

.paneHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.articleList {
  display: grid;
  gap: 12px;
}

.articleCard {
  display: grid;
  gap: 8px;
}

.articleCard h2 {
  margin: 0;
  font-size: 16px;
  line-height: 1.35;
}

.articleMeta,
.reason {
  color: var(--muted);
  font-size: 13px;
}

.scoreRow,
.scoreGrid,
.readerToolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.scoreBadge {
  display: inline-grid;
  grid-template-columns: auto auto;
  gap: 6px;
  align-items: center;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  padding: 4px 8px;
  font-size: 12px;
}

.content {
  max-width: 760px;
  font-size: 18px;
  line-height: 1.75;
}
```

- [ ] **Step 7: Build**

Run:

```bash
cd apps/reader-web
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/reader-web/src/app apps/reader-web/src/components
git commit -m "feat(reader-web): build desktop reading workbench"
```

---

## Task 9: Implement read, star, read-later, and feed management APIs

**Files:**
- Modify: `apps/reader-web/src/lib/miniflux/client.ts`
- Modify: `apps/reader-web/src/lib/scoring/repository.ts`
- Create: `apps/reader-web/src/app/api/articles/[id]/read/route.ts`
- Create: `apps/reader-web/src/app/api/articles/[id]/star/route.ts`
- Create: `apps/reader-web/src/app/api/articles/[id]/read-later/route.ts`
- Create: `apps/reader-web/src/app/api/feeds/route.ts`
- Create: `apps/reader-web/src/app/api/feeds/[id]/route.ts`
- Create: `apps/reader-web/src/app/api/feeds/[id]/refresh/route.ts`

- [ ] **Step 1: Extend Miniflux client methods**

Append methods to `MinifluxClient`:

```ts
  async updateEntries(entryIds: number[], status: "read" | "unread" | "removed") {
    const response = await fetch(new URL("/v1/entries", this.baseUrl), {
      method: "PUT",
      headers: {
        Authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString("base64")}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ entry_ids: entryIds, status }),
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Miniflux update entries failed: ${response.status}`);
  }

  async toggleBookmark(entryId: number) {
    const response = await fetch(new URL(`/v1/entries/${entryId}/bookmark`, this.baseUrl), {
      method: "PUT",
      headers: {
        Authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString("base64")}`,
      },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Miniflux bookmark failed: ${response.status}`);
  }

  async getFeeds() {
    const response = await fetch(new URL("/v1/feeds", this.baseUrl), {
      headers: {
        Authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString("base64")}`,
      },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Miniflux feeds request failed: ${response.status}`);
    return response.json();
  }

  async createFeed(feedUrl: string, categoryId: number) {
    const response = await fetch(new URL("/v1/feeds", this.baseUrl), {
      method: "POST",
      headers: {
        Authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString("base64")}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ feed_url: feedUrl, category_id: categoryId }),
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Miniflux create feed failed: ${response.status}`);
    return response.json();
  }

  async deleteFeed(feedId: number) {
    const response = await fetch(new URL(`/v1/feeds/${feedId}`, this.baseUrl), {
      method: "DELETE",
      headers: {
        Authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString("base64")}`,
      },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Miniflux delete feed failed: ${response.status}`);
  }

  async refreshFeed(feedId: number) {
    const response = await fetch(new URL(`/v1/feeds/${feedId}/refresh`, this.baseUrl), {
      method: "PUT",
      headers: {
        Authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString("base64")}`,
      },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Miniflux refresh feed failed: ${response.status}`);
  }
```

- [ ] **Step 2: Create helper for configured Miniflux client**

Append to `apps/reader-web/src/lib/miniflux/client.ts`:

```ts
import { getConfig } from "@/lib/config";

export function getMinifluxClient() {
  const config = getConfig();
  return new MinifluxClient(
    config.MINIFLUX_API_BASE_URL,
    config.MINIFLUX_USERNAME,
    config.MINIFLUX_PASSWORD,
  );
}
```

- [ ] **Step 3: Create read route**

Create `apps/reader-web/src/app/api/articles/[id]/read/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getMinifluxClient } from "@/lib/miniflux/client";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await getMinifluxClient().updateEntries([Number(id)], "read");
  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 4: Create star route**

Create `apps/reader-web/src/app/api/articles/[id]/star/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getMinifluxClient } from "@/lib/miniflux/client";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await getMinifluxClient().toggleBookmark(Number(id));
  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 5: Create read-later route**

Create `apps/reader-web/src/app/api/articles/[id]/read-later/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getConfig } from "@/lib/config";
import { getPool } from "@/lib/scoring/db";
import { setReadLaterSql } from "@/lib/scoring/repository";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json()) as { minifluxUserId: number; readLater: boolean };
  const config = getConfig();
  await getPool().query(
    setReadLaterSql({
      tenantId: config.READER_TENANT_ID,
      minifluxUserId: body.minifluxUserId,
      minifluxEntryId: Number(id),
      readLater: body.readLater,
    }),
  );
  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 6: Create feed routes**

Create `apps/reader-web/src/app/api/feeds/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getMinifluxClient } from "@/lib/miniflux/client";

export async function GET() {
  return NextResponse.json(await getMinifluxClient().getFeeds());
}

export async function POST(request: Request) {
  const body = (await request.json()) as { feedUrl: string; categoryId: number };
  return NextResponse.json(await getMinifluxClient().createFeed(body.feedUrl, body.categoryId));
}
```

Create `apps/reader-web/src/app/api/feeds/[id]/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getMinifluxClient } from "@/lib/miniflux/client";

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await getMinifluxClient().deleteFeed(Number(id));
  return NextResponse.json({ ok: true });
}
```

Create `apps/reader-web/src/app/api/feeds/[id]/refresh/route.ts`:

```ts
import { NextResponse } from "next/server";
import { getMinifluxClient } from "@/lib/miniflux/client";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await getMinifluxClient().refreshFeed(Number(id));
  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 7: Build**

Run:

```bash
cd apps/reader-web
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/reader-web/src/lib/miniflux/client.ts apps/reader-web/src/app/api
git commit -m "feat(reader-web): add reading state and feed APIs"
```

---

## Task 10: Implement current-article Agent streaming API

**Files:**
- Create: `apps/reader-web/src/lib/agent/prompt.ts`
- Create: `apps/reader-web/src/lib/agent/prompt.test.ts`
- Create: `apps/reader-web/src/lib/agent/webSearch.ts`
- Create: `apps/reader-web/src/lib/agent/minimax.ts`
- Create: `apps/reader-web/src/app/api/agent/article-chat/route.ts`

- [ ] **Step 1: Write failing prompt test**

Create `apps/reader-web/src/lib/agent/prompt.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import { buildArticleAgentMessages, shouldUseWebSearch } from "./prompt";

test("shouldUseWebSearch detects freshness questions", () => {
  assert.equal(shouldUseWebSearch("这个库现在还推荐用吗？版本是不是最新？"), true);
  assert.equal(shouldUseWebSearch("总结这篇文章"), false);
});

test("buildArticleAgentMessages includes selected quote", () => {
  const messages = buildArticleAgentMessages({
    question: "解释这段",
    article: {
      title: "Agent Article",
      url: "https://example.com",
      contentText: "Full content",
      scoreReason: "High technical value",
      tags: ["ai"],
    },
    selectedText: "Important quote",
    searchResults: [],
  });

  const serialized = JSON.stringify(messages);
  assert.match(serialized, /Important quote/);
  assert.match(serialized, /High technical value/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/agent/prompt.test.ts
```

Expected: FAIL because prompt module does not exist.

- [ ] **Step 3: Implement Agent prompt helpers**

Create `apps/reader-web/src/lib/agent/prompt.ts`:

```ts
type AgentInput = {
  question: string;
  article: {
    title: string;
    url: string;
    contentText: string;
    scoreReason: string;
    tags: string[];
  };
  selectedText?: string;
  searchResults: { title: string; url: string; snippet: string }[];
};

export function shouldUseWebSearch(question: string): boolean {
  return /最新|现在|版本|推荐|公司|产品|新闻|趋势|是否过时|current|latest|version/i.test(question);
}

export function buildArticleAgentMessages(input: AgentInput) {
  const searchBlock = input.searchResults.length
    ? input.searchResults
        .map((result, index) => `${index + 1}. ${result.title}\n${result.url}\n${result.snippet}`)
        .join("\n\n")
    : "未使用联网搜索。";

  return [
    {
      role: "system",
      content:
        "你是一个 RSS 当前文章阅读助手。回答必须结构化，包含：结论、依据、引用、不确定点、行动建议。不要展示隐藏推理链。涉及事实时优先引用搜索结果。",
    },
    {
      role: "user",
      content: `问题：${input.question}

文章标题：${input.article.title}
文章 URL：${input.article.url}
AI 评分理由：${input.article.scoreReason}
标签：${input.article.tags.join(", ")}

用户选中文字：
${input.selectedText || "无"}

文章正文：
${input.article.contentText.slice(0, 12000)}

联网搜索结果：
${searchBlock}`,
    },
  ];
}
```

- [ ] **Step 4: Implement web search client with explicit no-provider behavior**

Create `apps/reader-web/src/lib/agent/webSearch.ts`:

```ts
import { getConfig } from "@/lib/config";

export type WebSearchResult = {
  title: string;
  url: string;
  snippet: string;
};

export async function searchWeb(query: string): Promise<WebSearchResult[]> {
  const config = getConfig();
  if (config.WEB_SEARCH_PROVIDER === "none") return [];
  if (config.WEB_SEARCH_PROVIDER !== "brave" || !config.WEB_SEARCH_API_KEY) return [];

  const url = new URL("https://api.search.brave.com/res/v1/web/search");
  url.searchParams.set("q", query);
  url.searchParams.set("count", "5");

  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      "X-Subscription-Token": config.WEB_SEARCH_API_KEY,
    },
    cache: "no-store",
  });
  if (!response.ok) return [];
  const data = (await response.json()) as {
    web?: { results?: { title?: string; url?: string; description?: string }[] };
  };
  return (data.web?.results ?? []).map((item) => ({
    title: item.title ?? "",
    url: item.url ?? "",
    snippet: item.description ?? "",
  }));
}
```

- [ ] **Step 5: Implement Minimax streaming client**

Create `apps/reader-web/src/lib/agent/minimax.ts`:

```ts
import { getConfig } from "@/lib/config";

export async function streamMinimaxChat(messages: { role: string; content: string }[]) {
  const config = getConfig();
  if (!config.MINIMAX_API_KEY || !config.MINIMAX_BASE_URL || !config.MINIMAX_MODEL) {
    throw new Error("Minimax Agent environment variables are not configured");
  }

  const response = await fetch(`${config.MINIMAX_BASE_URL.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.MINIMAX_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: config.MINIMAX_MODEL,
      messages,
      stream: true,
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Minimax Agent request failed: ${response.status}`);
  }

  return response.body;
}
```

- [ ] **Step 6: Create streaming route**

Create `apps/reader-web/src/app/api/agent/article-chat/route.ts`:

```ts
import { buildArticleAgentMessages, shouldUseWebSearch } from "@/lib/agent/prompt";
import { streamMinimaxChat } from "@/lib/agent/minimax";
import { searchWeb } from "@/lib/agent/webSearch";

export async function POST(request: Request) {
  const body = (await request.json()) as {
    question: string;
    selectedText?: string;
    article: {
      title: string;
      url: string;
      contentText: string;
      scoreReason: string;
      tags: string[];
    };
  };

  const searchResults = shouldUseWebSearch(body.question)
    ? await searchWeb(`${body.question} ${body.article.title}`)
    : [];

  const messages = buildArticleAgentMessages({
    question: body.question,
    selectedText: body.selectedText,
    article: body.article,
    searchResults,
  });

  const stream = await streamMinimaxChat(messages);
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
```

- [ ] **Step 7: Run tests and build**

Run:

```bash
cd apps/reader-web
npm test -- src/lib/agent/prompt.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/reader-web/src/lib/agent apps/reader-web/src/app/api/agent
git commit -m "feat(reader-web): add streaming article agent"
```

---

## Task 11: Add Agent panel and selected-text quote workflow

**Files:**
- Create: `apps/reader-web/src/components/AgentPanel.tsx`
- Modify: `apps/reader-web/src/components/ArticleReader.tsx`
- Modify: `apps/reader-web/src/app/globals.css`

- [ ] **Step 1: Create client Agent panel**

Create `apps/reader-web/src/components/AgentPanel.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { Article } from "@/lib/articles/types";

const quickActions = [
  "总结这篇文章",
  "提炼 5 个要点",
  "解释关键术语",
  "这篇为什么值得读",
  "和我的 RSS / AI / 工程项目有什么关系",
  "给我一个行动建议",
];

export function AgentPanel({ article }: { article: Article }) {
  const [question, setQuestion] = useState("");
  const [selectedText, setSelectedText] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

  function captureSelection() {
    setSelectedText(window.getSelection()?.toString() ?? "");
  }

  async function askAgent(nextQuestion = question) {
    setLoading(true);
    setAnswer("");
    const response = await fetch("/api/agent/article-chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: nextQuestion,
        selectedText,
        article: {
          title: article.title,
          url: article.url,
          contentText: article.contentHtml.replace(/<[^>]+>/g, " "),
          scoreReason: article.score?.reason ?? "",
          tags: article.score?.tags ?? [],
        },
      }),
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    if (!reader) {
      setLoading(false);
      return;
    }
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      setAnswer((current) => current + decoder.decode(value, { stream: true }));
    }
    setLoading(false);
  }

  return (
    <aside className="agentPanel">
      <div className="agentHeader">
        <strong>当前文章 Agent</strong>
        <button type="button" onClick={captureSelection}>引用选中文字</button>
      </div>
      {selectedText ? <blockquote>{selectedText}</blockquote> : null}
      <div className="quickActions">
        {quickActions.map((action) => (
          <button type="button" key={action} onClick={() => askAgent(action)}>
            {action}
          </button>
        ))}
      </div>
      <textarea
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        aria-label="围绕当前文章继续追问"
      />
      <button type="button" disabled={loading || !question} onClick={() => askAgent()}>
        {loading ? "生成中..." : "发送"}
      </button>
      <pre className="agentAnswer">{answer}</pre>
    </aside>
  );
}
```

- [ ] **Step 2: Render Agent panel in reader**

Modify `apps/reader-web/src/components/ArticleReader.tsx`:

```tsx
import { AgentPanel } from "./AgentPanel";
```

Add below the article content:

```tsx
      <AgentPanel article={article} />
```

- [ ] **Step 3: Add Agent styles**

Append to `apps/reader-web/src/app/globals.css`:

```css
.agentPanel {
  margin-top: 32px;
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px;
  background: #f9fafb;
}

.agentHeader,
.quickActions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.quickActions {
  justify-content: flex-start;
  margin: 12px 0;
}

.agentPanel textarea {
  min-height: 90px;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
}

.agentAnswer {
  white-space: pre-wrap;
  font-family: inherit;
  line-height: 1.6;
}
```

- [ ] **Step 4: Build**

Run:

```bash
cd apps/reader-web
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/reader-web/src/components apps/reader-web/src/app/globals.css
git commit -m "feat(reader-web): add current article agent panel"
```

---

## Task 12: Wire deployment config for reader-web

**Files:**
- Modify: `.env.example`
- Modify: `infra/compose/docker-compose.base.yml`
- Modify: `infra/compose/docker-compose.prod.yml`
- Modify: `infra/compose/docker-compose.staging.yml`
- Create: `infra/caddy/conf.d/reader-web.caddy`

- [ ] **Step 1: Update `.env.example`**

Add:

```dotenv
READER_TENANT_ID=default
WEB_SEARCH_PROVIDER=none
WEB_SEARCH_API_KEY=change_me
AI_READER_HOST=ai-reader
STAGING_AI_READER_HOST=staging-ai-reader
```

- [ ] **Step 2: Add reader-web service to base compose**

Add under `services:` in `infra/compose/docker-compose.base.yml`:

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
      MINIMAX_API_KEY: ${MINIMAX_API_KEY}
      MINIMAX_BASE_URL: ${MINIMAX_BASE_URL}
      MINIMAX_MODEL: ${MINIMAX_MODEL}
      WEB_SEARCH_PROVIDER: ${WEB_SEARCH_PROVIDER}
      WEB_SEARCH_API_KEY: ${WEB_SEARCH_API_KEY}
    networks:
      - app
      - data
```

- [ ] **Step 3: Add network aliases**

In `infra/compose/docker-compose.prod.yml`, add a `reader-web` override with alias:

```yaml
  reader-web:
    networks:
      app:
        aliases:
          - reader-web-prod
      data: {}
```

In `infra/compose/docker-compose.staging.yml`, add:

```yaml
  reader-web:
    networks:
      app:
        aliases:
          - reader-web-staging
      data: {}
```

- [ ] **Step 4: Add Caddy routes**

Create `infra/caddy/conf.d/reader-web.caddy`:

```caddyfile
ai-reader.{$DOMAIN} {
    handle /healthz {
        reverse_proxy reader-web-prod:3000
    }

    handle {
        forward_auth authelia-prod:9091 {
            uri /api/authz/forward-auth
            copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
        }
        reverse_proxy reader-web-prod:3000
    }
}

staging-ai-reader.{$DOMAIN} {
    handle /healthz {
        reverse_proxy reader-web-staging:3000
    }

    handle {
        forward_auth authelia-staging:9091 {
            uri /api/authz/forward-auth
            copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
        }
        reverse_proxy reader-web-staging:3000
    }
}
```

- [ ] **Step 5: Validate compose config**

Run:

```bash
docker compose \
  --env-file .env.example \
  -f infra/compose/docker-compose.base.yml \
  -f infra/compose/docker-compose.prod.yml \
  config >/tmp/myrss-reader-web-compose.yml
```

Expected: command exits 0 and generated config contains `reader-web`.

- [ ] **Step 6: Commit**

```bash
git add .env.example infra/compose/docker-compose.base.yml infra/compose/docker-compose.prod.yml infra/compose/docker-compose.staging.yml infra/caddy/conf.d/reader-web.caddy
git commit -m "feat(infra): route AI reader web service"
```

---

## Task 13: Add learning notes, run full verification, and clean generated files

**Files:**
- Modify: `docs/learning-notes.md`
- Verify: `apps/scorer-worker/**`
- Verify: `apps/reader-web/**`
- Verify: `infra/compose/**`

- [ ] **Step 1: Add learning notes section**

Append to `docs/learning-notes.md`:

```markdown
## Task：AI 阅读工作台实现

### 做了什么

新增 `reader-web` 作为日常阅读入口，并让 Miniflux 继续作为 RSS 后端。评分系统升级为综合分 + 多维分，新前端可以按模块和维度排序文章。

### 关键概念

**前端服务与 RSS 后端分离**
Miniflux 负责稳定抓取和状态管理，新前端负责阅读体验。这样不用 fork Miniflux，也不会因为 Miniflux 升级而反复处理冲突。

**流式 Agent**
Agent 输出通过 streaming response 返回，用户可以边生成边阅读。弱模型响应慢或不稳定时，流式输出能明显降低等待感。

**联网搜索边界**
不是所有问题都需要搜索。总结当前文章可以只用文章正文；涉及最新事实、版本、公司、新闻和趋势时才联网查证。

### 可以在学习 session 里追问的问题

- Next.js Route Handler 和传统后端 API 有什么区别？
- 为什么 reader-web 需要同时访问 Miniflux API 和 scoring DB？
- 多维分数如何影响推荐排序？
- Agent 的流式响应是怎么从后端传到浏览器的？
```

- [ ] **Step 2: Remove generated Python cache files from working tree**

Run:

```bash
python - <<'PY'
from pathlib import Path
for path in Path("apps/scorer-worker").rglob("__pycache__"):
    for child in path.iterdir():
        child.unlink()
PY
```

Expected: no Python cache files remain under `apps/scorer-worker`.

- [ ] **Step 3: Run scorer verification**

Run:

```bash
cd apps/scorer-worker
python -m pytest -v
python -m ruff check src tests
```

Expected: PASS.

- [ ] **Step 4: Run reader-web verification**

Run:

```bash
cd apps/reader-web
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 5: Run compose verification**

Run:

```bash
docker compose \
  --env-file .env.example \
  -f infra/compose/docker-compose.base.yml \
  -f infra/compose/docker-compose.prod.yml \
  config >/tmp/myrss-reader-web-compose.yml
```

Expected: PASS.

- [ ] **Step 6: Inspect git status**

Run:

```bash
git status --short
```

Expected: only intentional implementation files are modified or untracked.

- [ ] **Step 7: Commit final docs and cleanup**

```bash
git add docs/learning-notes.md
git commit -m "docs: document AI reader implementation notes"
```

---

## Self-Review Checklist

- Spec coverage:
  - New `reader-web` service: Tasks 4, 8, 12.
  - Multidimensional scoring: Tasks 1-2.
  - Modules and sorting: Tasks 6-8.
  - Miniflux-backed read/star/feed management: Tasks 5, 7, 9.
  - Read-later custom state: Tasks 3, 9.
  - Current article Agent, selected text, streaming, web search: Tasks 10-11.
  - Error handling and verification: Tasks 7, 10, 13.
- Completion marker scan:
  - This plan intentionally uses no unfinished markers, no incomplete sections, and no vague error-handling steps.
- Type consistency:
  - `Article`, `ArticleScore`, `DimensionKey`, and `ModuleId` are defined before use.
  - API route names match the design spec.
  - `dimension_scores` is consistently JSONB in SQL and `dimensions` in frontend types.

# RSS MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在单台 Debian VPS 上交付可用的 RSS MVP（Miniflux + Authelia + Caddy + PostgreSQL + 批处理评分 Worker + CI/CD + 发布前审计）。

**Architecture:** 采用网关前置认证与旁路评分架构。单实例共享 Caddy 作为唯一 80/443 入口，按 prod/staging 别名路由到后端；主链路由 Authelia 保护 Miniflux，评分 Worker 通过 Miniflux API 拉取数据并写入独立评分库。发布流程通过 GitHub Actions 分离 staging/prod，发布前执行轻量审计清单。

**Tech Stack:** Docker Compose, Caddy, Authelia, Miniflux v2, PostgreSQL 16, Python 3.12 (Worker), GitHub Actions, Trivy

---

> Plan v3 hardening update: 修复 staging/prod 端口冲突、三层网络边界、PostgreSQL 初始化、持久化卷、Authelia secrets 与访问规则、Worker 调度、CI 供应链风险与发布门禁。

## File Structure

- `infra/compose/`：edge/base/staging/prod 的容器编排
- `infra/caddy/`：HTTPS 与反向代理配置
- `infra/authelia/`：认证网关配置与用户目录
- `infra/scripts/`：部署、回滚、备份、恢复脚本
- `apps/scorer-worker/`：评分 Worker
- `apps/scorer-worker/tests/`：Worker 测试
- `.github/workflows/`：CI/CD 工作流
- `docs/superpowers/specs/`：冻结设计与审计清单
- `docs/runbooks/`：运维手册

---

## Learning Outcomes By Task (Execution Companion)

> 用法：每完成一个 Task，先回答“自测问题”，再进入下一个 Task。  
> 目标：不是只跑通命令，而是理解“为什么这样设计”。

| Task | 你要学会什么 | 动手观察点 | 自测问题（执行后回答） |
|---|---|---|---|
| Task 1 | 基础工程骨架与配置分层 | `.env.example` 与 compose 文件职责边界 | 为什么 `.env.example` 只能放模板，不能放真实 secret？ |
| Task 2 | 认证前置网关与反代链路 | `reader/auth` 路由差异、`forward_auth` 行为 | 为什么 `reader` 不能直接反代到 Authelia？ |
| Task 3 | 业务服务与数据库最小可用配置 | Miniflux 环境变量、Postgres 端口隔离 | 为什么“Postgres 不暴露公网”比“只靠密码”更关键？ |
| Task 4 | TDD 最小闭环（Fail -> Pass） | `pytest` 先失败再通过 | 为什么先写 failing test 能减少后续返工？ |
| Task 5 | 幂等写入与重跑安全 | `ON CONFLICT ... DO UPDATE` | 如果同一条目重评 3 次，数据库如何保证不脏写？ |
| Task 6 | 可追溯发布与灾备基础 | `deploy/rollback/backup/restore` 脚本参数 | 为什么部署脚本必须显式消费 `TAG`？ |
| Task 7 | CI/CD 门禁与供应链检查 | PR 检查项、Trivy 扫描结果 | 哪些检查应该是“阻断型”，为什么？ |
| Task 8 | 运维知识沉淀与证据联动 | Runbook 与审计清单互相引用 | 没有 runbook 时，事故恢复会卡在哪一步？ |
| Task 9 | 预发验证与生产回滚演练 | staging -> prod -> rollback 全链路 | 为什么“演练过的回滚”比“写在文档里的回滚”更可靠？ |

### Learning Gate (Mandatory)

- [ ] 每个 Task 完成后，写 3 行学习记录：做了什么、为什么这么做、下次如何复现。
- [ ] 每个 High 风险点至少留 1 条可复现证据（命令 + 输出路径）。
- [ ] 每完成 2 个 Task，做一次 10 分钟复盘：是否偏离“最小可用 + 可复现”目标。

### Session Log Template (Copy Per Task)

```markdown
#### Task X Learning Log
- What I changed:
- Why this design:
- Command(s) I ran:
- Evidence path:
- What failed and how I fixed it:
- How I would reproduce this on a new server:
```

---

### Task 1: 初始化仓库结构与环境变量模板

**Files:**
- Create: `infra/compose/docker-compose.base.yml`
- Create: `infra/compose/docker-compose.edge.yml`
- Create: `infra/compose/docker-compose.staging.yml`
- Create: `infra/compose/docker-compose.prod.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Test: `README bootstrap check`

- [ ] **Step 1: 创建 `.gitignore` 与 `.env.example`**

```dotenv
# .env.example
DOMAIN=example.com
MINIFLUX_ADMIN=admin
MINIFLUX_ADMIN_PASSWORD=change_me
POSTGRES_SUPERUSER_PASSWORD=change_me
POSTGRES_MINIFLUX_PASSWORD=change_me
POSTGRES_SCORING_PASSWORD=change_me
MINIFLUX_DATABASE_URL=postgres://miniflux:change_me@postgres:5432/miniflux?sslmode=disable
SCORING_DATABASE_URL=postgres://scoring:change_me@postgres:5432/scoring?sslmode=disable
MINIFLUX_API_BASE_URL=http://miniflux:8080
MINIFLUX_API_KEY=change_me
SCORER_INTERVAL_SECONDS=3600
SCORER_TENANT_ID=default
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=mailer@example.com
SMTP_PASSWORD=change_me
```

- [ ] **Step 2: 创建唯一公网入口 Compose（edge）**

```yaml
# infra/compose/docker-compose.edge.yml
services:
  caddy:
    image: caddy:2.8
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ../caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - edge
      - app

networks:
  edge:
  app:
    name: myrss-edge
    external: true

volumes:
  caddy_data:
  caddy_config:
```

- [ ] **Step 3: 创建基础 Compose 文件（base，三层网络）**

```yaml
# infra/compose/docker-compose.base.yml
services:
  authelia:
    image: authelia/authelia:latest
    restart: unless-stopped
    networks: [app]
    volumes:
      - authelia_data:/config
    environment:
      AUTHELIA_SESSION_SECRET_FILE: /run/secrets/authelia_session_secret
      AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE: /run/secrets/authelia_storage_encryption_key
  postgres:
    image: postgres:16
    restart: unless-stopped
    networks: [data]
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD}
      POSTGRES_MINIFLUX_PASSWORD: ${POSTGRES_MINIFLUX_PASSWORD}
      POSTGRES_SCORING_PASSWORD: ${POSTGRES_SCORING_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ../postgres/init:/docker-entrypoint-initdb.d:ro
  miniflux:
    image: miniflux/miniflux:latest
    restart: unless-stopped
    networks: [app, data]
    environment:
      DATABASE_URL: ${MINIFLUX_DATABASE_URL}
      BASE_URL: https://reader.${DOMAIN}
      LISTEN_ADDR: 0.0.0.0:8080
  scorer-worker:
    build: ../../apps/scorer-worker
    restart: unless-stopped
    networks: [app, data]
    environment:
      MINIFLUX_API_BASE_URL: ${MINIFLUX_API_BASE_URL}
      MINIFLUX_API_KEY: ${MINIFLUX_API_KEY}
      SCORING_DATABASE_URL: ${SCORING_DATABASE_URL}
      SCORER_INTERVAL_SECONDS: ${SCORER_INTERVAL_SECONDS}
      SCORER_TENANT_ID: ${SCORER_TENANT_ID}
networks:
  app:
    name: myrss-edge
    external: true
  data:
volumes:
  postgres_data:
  authelia_data:
```

- [ ] **Step 4: 运行快速结构检查**

Run: `rg "services:|networks:|edge|app|data|postgres_data|authelia_data" infra/compose/docker-compose.base.yml infra/compose/docker-compose.edge.yml .env.example`  
Expected: 输出匹配行且退出码为 0，且 edge/base 分层清晰

- [ ] **Step 5: Commit**

Run:
```bash
git add .gitignore .env.example infra/compose/docker-compose.edge.yml infra/compose/docker-compose.base.yml infra/compose/docker-compose.staging.yml infra/compose/docker-compose.prod.yml
git commit -m "chore: bootstrap project structure and env templates"
```

### Task 2: 配置 Caddy 与 Authelia 入口认证

**Files:**
- Create: `infra/caddy/Caddyfile`
- Create: `infra/authelia/configuration.yml`
- Create: `infra/authelia/users_database.yml`
- Test: `infra/scripts/smoke-auth.sh`

- [ ] **Step 1: 写入 Caddy 路由配置（prod + staging）**

```caddy
reader.{$DOMAIN} {
  forward_auth authelia-prod:9091 {
    uri /api/authz/forward-auth
    copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
  }
  reverse_proxy miniflux-prod:8080
}
auth.{$DOMAIN} {
  reverse_proxy authelia-prod:9091
}
staging-reader.{$DOMAIN} {
  forward_auth authelia-staging:9091 {
    uri /api/authz/forward-auth
    copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
  }
  reverse_proxy miniflux-staging:8080
}
staging-auth.{$DOMAIN} {
  reverse_proxy authelia-staging:9091
}
```

- [ ] **Step 2: 写入 Authelia 配置骨架（使用 _FILE secrets + allow rules）**

```yaml
# infra/authelia/configuration.yml
authentication_backend:
  file:
    path: /config/users_database.yml
totp:
  issuer: my_rss
webauthn:
  disable: false
access_control:
  default_policy: deny
  rules:
    - domain:
        - reader.example.com
        - staging-reader.example.com
      policy: two_factor
session:
  name: authelia_session
  same_site: lax
  inactivity: 30m
  expiration: 8h
  remember_me: 7d
  cookies:
    - domain: example.com
      authelia_url: https://auth.example.com
      default_redirection_url: https://reader.example.com
storage:
  encryption_key: "replace_with_64_chars_random_string"
  local:
    path: /config/db.sqlite3
```

- [ ] **Step 3: 在 compose 中配置服务网络别名（prod/staging）**

```yaml
# prod
miniflux:
  networks:
    app:
      aliases: [miniflux-prod]
    data: {}
authelia:
  networks:
    app:
      aliases: [authelia-prod]
```

```yaml
# staging
miniflux:
  networks:
    app:
      aliases: [miniflux-staging]
    data: {}
authelia:
  networks:
    app:
      aliases: [authelia-staging]
```

- [ ] **Step 4: 写入本地用户样例**

```yaml
users:
  admin:
    disabled: false
    displayname: "Admin"
    password: "$argon2id$replace_with_generated_hash"
    email: "admin@example.com"
```

- [ ] **Step 5: 执行配置语法检查**

Run: `rg "default_policy: deny|rules:|AUTHELIA_SESSION_SECRET_FILE|AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE" infra/authelia/configuration.yml infra/compose/docker-compose.base.yml`  
Expected: 命中 deny + allow rules 与 _FILE secret 配置

- [ ] **Step 6: 准备 secret 文件挂载（或 Docker secrets）**

```bash
# 示例：以 bind mount secret 文件方式注入（文件权限 600）
mkdir -p /opt/myrss/secrets
openssl rand -hex 32 > /opt/myrss/secrets/authelia_session_secret
openssl rand -hex 32 > /opt/myrss/secrets/authelia_storage_encryption_key
```

- [ ] **Step 7: 验证认证链路设计正确**

Run: `rg "forward_auth|authelia-prod|authelia-staging|miniflux-prod|miniflux-staging" infra/caddy/Caddyfile -n`  
Expected: 同时命中 prod/staging 的 forward_auth 与反代目标

- [ ] **Step 8: 在计划中记录 MVP 双登录预期**

```markdown
MVP 阶段接受“双登录”：
- Authelia 负责入口保护；
- Miniflux 保留本地账号登录；
- OIDC/Auth Proxy（AUTH_PROXY_HEADER + TRUSTED_REVERSE_PROXY_NETWORKS）放在后续阶段。
```

- [ ] **Step 9: Commit**

Run:
```bash
git add infra/caddy/Caddyfile infra/authelia/configuration.yml infra/authelia/users_database.yml infra/compose/docker-compose.staging.yml infra/compose/docker-compose.prod.yml
git commit -m "feat: harden caddy and authelia gateway topology"
```

### Task 3: 落地 Miniflux 与 PostgreSQL 运行配置

**Files:**
- Modify: `infra/compose/docker-compose.base.yml`
- Modify: `infra/compose/docker-compose.staging.yml`
- Modify: `infra/compose/docker-compose.prod.yml`
- Create: `infra/postgres/init/001-create-databases.sh`
- Test: `infra/scripts/smoke-stack.sh`

- [ ] **Step 1: 增加 Miniflux 环境变量（含 BASE_URL 与监听地址）**

```yaml
miniflux:
  environment:
    DATABASE_URL: ${MINIFLUX_DATABASE_URL}
    RUN_MIGRATIONS: "1"
    CREATE_ADMIN: "1"
    ADMIN_USERNAME: ${MINIFLUX_ADMIN}
    ADMIN_PASSWORD: ${MINIFLUX_ADMIN_PASSWORD}
    BASE_URL: https://reader.${DOMAIN}
    LISTEN_ADDR: 0.0.0.0:8080
```

- [ ] **Step 2: 增加 PostgreSQL 初始化脚本挂载与专用用户初始化**

```bash
#!/usr/bin/env bash
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
  CREATE USER miniflux WITH PASSWORD '${POSTGRES_MINIFLUX_PASSWORD}';
  CREATE DATABASE miniflux OWNER miniflux;

  CREATE USER scoring WITH PASSWORD '${POSTGRES_SCORING_PASSWORD}';
  CREATE DATABASE scoring OWNER scoring;
EOSQL
```

- [ ] **Step 3: 挂载 PostgreSQL init 目录**

```yaml
postgres:
  environment:
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD}
    POSTGRES_MINIFLUX_PASSWORD: ${POSTGRES_MINIFLUX_PASSWORD}
    POSTGRES_SCORING_PASSWORD: ${POSTGRES_SCORING_PASSWORD}
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ../postgres/init:/docker-entrypoint-initdb.d:ro
```

- [ ] **Step 4: 确保 Postgres 无公网端口映射**

Run: `rg "postgres:|ports:" infra/compose/docker-compose.base.yml -n`  
Expected: 只有 edge Caddy 有 80/443 映射，`postgres` 无端口映射

- [ ] **Step 5: 本地 compose 配置检查**

Run: `docker compose -f infra/compose/docker-compose.edge.yml -f infra/compose/docker-compose.base.yml config`  
Expected: `services` 渲染成功，命令退出码 0

- [ ] **Step 6: Commit**

Run:
```bash
git add infra/compose/docker-compose.base.yml infra/compose/docker-compose.staging.yml infra/compose/docker-compose.prod.yml infra/postgres/init/001-create-databases.sh .env.example
git commit -m "feat: configure miniflux and postgres runtime with init bootstrap"
```

### Task 3.5: 创建 Worker 专用 Miniflux API Key（新增）

**Files:**
- Modify: `docs/runbooks/deploy.md`
- Modify: `.env.example`
- Test: `secret injection checklist`

- [ ] **Step 1: 在 Miniflux 管理界面创建 scorer-worker 专用 API Key**
- [ ] **Step 2: 写入服务器 secret 文件（不入库）**
- [ ] **Step 3: Worker 通过 `MINIFLUX_API_KEY_FILE` 或环境变量读取**
- [ ] **Step 4: 在 runbook 记录轮换步骤与失效策略（创建新 key -> worker 切换 -> 验证 -> 删除旧 key）**
- [ ] **Step 5: Commit**

### Task 4: 实现评分 Worker 最小可运行版本

**Files:**
- Create: `apps/scorer-worker/pyproject.toml`
- Create: `apps/scorer-worker/src/main.py`
- Create: `apps/scorer-worker/src/miniflux_client.py`
- Create: `apps/scorer-worker/src/scoring.py`
- Test: `apps/scorer-worker/tests/test_scoring.py`

- [ ] **Step 1: 写 failing test（评分输出结构）**

```python
def test_score_payload_shape():
    payload = score_entry({"id": 1, "title": "hello", "content": "world"})
    assert set(payload.keys()) == {
        "score", "tags", "reason", "model_version",
        "model_provider", "model_name", "prompt_version",
        "confidence", "scoring_status", "error_message",
    }
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest apps/scorer-worker/tests/test_scoring.py::test_score_payload_shape -v`  
Expected: FAIL（`score_entry` 未定义或导入失败）

- [ ] **Step 3: 写最小实现（含循环调度）**

```python
while True:
    # 1) fetch recent entries from Miniflux API
    # 2) upsert items_snapshot
    # 3) score unscored entries
    # 4) upsert item_scores
    # 5) sleep interval
    run_once()
    time.sleep(int(os.getenv("SCORER_INTERVAL_SECONDS", "3600")))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest apps/scorer-worker/tests/test_scoring.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add apps/scorer-worker
git commit -m "feat: add baseline scorer worker with scheduler loop"
```

### Task 5: 定义评分库 schema 与数据持久化

**Files:**
- Create: `apps/scorer-worker/sql/001_init_scoring.sql`
- Create: `apps/scorer-worker/src/repository.py`
- Test: `apps/scorer-worker/tests/test_repository.py`

- [ ] **Step 1: 编写 schema（items_snapshot/item_scores/scoring_jobs/export_cursor/feed_health）**

```sql
CREATE TABLE IF NOT EXISTS items_snapshot (...);

CREATE TABLE IF NOT EXISTS item_scores (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  miniflux_entry_id BIGINT NOT NULL,
  content_hash TEXT NOT NULL,
  score INT NOT NULL,
  tags JSONB NOT NULL,
  reason TEXT NOT NULL,
  model_version TEXT NOT NULL,
  model_provider TEXT NOT NULL DEFAULT 'baseline',
  model_name TEXT NOT NULL DEFAULT 'length-baseline',
  prompt_version TEXT NOT NULL DEFAULT 'none',
  confidence NUMERIC(4,3),
  scoring_status TEXT NOT NULL DEFAULT 'success',
  error_message TEXT,
  scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, miniflux_entry_id, content_hash, model_version)
);

CREATE TABLE IF NOT EXISTS scoring_jobs (...);
CREATE TABLE IF NOT EXISTS export_cursor (...);
CREATE TABLE IF NOT EXISTS feed_health (...);
```

- [ ] **Step 2: 编写 repository 幂等写入逻辑**

```python
def upsert_score(conn, row):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO item_scores (
              tenant_id, miniflux_entry_id, content_hash,
              score, tags, reason, model_version,
              model_provider, model_name, prompt_version,
              confidence, scoring_status, error_message
            ) VALUES (
              %(tenant_id)s, %(miniflux_entry_id)s, %(content_hash)s,
              %(score)s, %(tags)s::jsonb, %(reason)s, %(model_version)s,
              %(model_provider)s, %(model_name)s, %(prompt_version)s,
              %(confidence)s, %(scoring_status)s, %(error_message)s
            )
            ON CONFLICT (tenant_id, miniflux_entry_id, content_hash, model_version)
            DO UPDATE SET
              score = EXCLUDED.score,
              tags = EXCLUDED.tags,
              reason = EXCLUDED.reason,
              confidence = EXCLUDED.confidence,
              scoring_status = EXCLUDED.scoring_status,
              error_message = EXCLUDED.error_message,
              scored_at = NOW();
            """,
            row,
        )
    conn.commit()
```

- [ ] **Step 3: 写并运行 repository 测试**

Run: `pytest apps/scorer-worker/tests/test_repository.py -v`  
Expected: PASS（覆盖冲突更新路径）

- [ ] **Step 4: Commit**

Run:
```bash
git add apps/scorer-worker/sql/001_init_scoring.sql apps/scorer-worker/src/repository.py apps/scorer-worker/tests/test_repository.py
git commit -m "feat: add full scoring schema and idempotent repository writes"
```

### Task 6: 加入运维脚本（部署/回滚/备份/恢复）

**Files:**
- Create: `infra/scripts/deploy.sh`
- Create: `infra/scripts/rollback.sh`
- Create: `infra/scripts/backup.sh`
- Create: `infra/scripts/restore.sh`
- Test: `infra/scripts/check-scripts.sh`

- [ ] **Step 1: 写部署脚本（edge 单例 + env 后端）**

```bash
#!/usr/bin/env bash
set -euo pipefail
ENV="$1"; TAG="$2"

# 只部署一次共享边缘入口
IMAGE_TAG="$TAG" docker compose -p "myrss-edge" \
  -f infra/compose/docker-compose.edge.yml up -d --remove-orphans

# 部署环境后端（不再抢占 80/443）
IMAGE_TAG="$TAG" docker compose -p "myrss-${ENV}" \
  -f infra/compose/docker-compose.base.yml \
  -f "infra/compose/docker-compose.${ENV}.yml" up -d --remove-orphans
```

- [ ] **Step 2: 写备份与恢复脚本（pg_dump/pg_restore）**

```bash
pg_dump -Fc miniflux > "backup/miniflux-${TS}.dump"
pg_dump -Fc scoring > "backup/scoring-${TS}.dump"
sha256sum "backup/miniflux-${TS}.dump" "backup/scoring-${TS}.dump" > "backup/checksums-${TS}.txt"
```

- [ ] **Step 3: 赋执行权限并做 shellcheck**

Run: `chmod +x infra/scripts/*.sh && shellcheck infra/scripts/*.sh`  
Expected: shellcheck 无 error 级别问题

- [ ] **Step 4: Commit**

Run:
```bash
git add infra/scripts
git commit -m "feat: add deploy rollback backup and restore scripts"
```

### Task 7: 建立 GitHub Actions CI/CD 流程

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/deploy-staging.yml`
- Create: `.github/workflows/deploy-prod.yml`
- Create: `.github/workflows/rollback.yml`
- Create: `.github/CODEOWNERS`
- Create: `.github/pull_request_template.md`
- Test: `GitHub Actions workflow lint`

- [ ] **Step 1: 写 `ci.yml`（lint/test/build/trivy）**

```yaml
name: ci
on: [pull_request]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -U pip pytest ruff
      - run: ruff check apps/scorer-worker
      - run: pytest apps/scorer-worker/tests -q
      - run: docker compose -f infra/compose/docker-compose.base.yml config > /tmp/compose.rendered.yml
      - uses: aquasecurity/trivy-action@0.35.0
        with:
          scan-type: "fs"
          scan-ref: "."
          format: "table"
```

- [ ] **Step 2: 写 staging/prod/rollback 工作流骨架（prod 加 environment gate）**

```yaml
on:
  push:
    branches: [develop]
```

```yaml
on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: "Image tag to deploy/rollback"
        required: true
        type: string
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
```

- [ ] **Step 3: 配置 CODEOWNERS 高风险目录**

```txt
infra/** @blankhoney
apps/scorer-worker/** @blankhoney
.github/workflows/** @blankhoney
```

- [ ] **Step 4: 配置 GitHub branch protection / ruleset（强制 Code Owner Review）**

```markdown
main:
- require PR before merge
- require status checks
- require review from Code Owners
- block force push
- block deletion

develop:
- require PR before merge
- require status checks
```

- [ ] **Step 5: Commit**

Run:
```bash
git add .github/workflows .github/CODEOWNERS .github/pull_request_template.md
git commit -m "feat: add github actions pipeline and deployment gates"
```

### Task 8: 编写 Runbook 与发布前审计联动

**Files:**
- Create: `docs/runbooks/deploy.md`
- Create: `docs/runbooks/rollback.md`
- Create: `docs/runbooks/backup-restore.md`
- Modify: `docs/superpowers/specs/2026-05-11-rss-audit-checklist.md`
- Test: `docs cross-reference check`

- [ ] **Step 1: 写部署/回滚/备份恢复操作手册（健康检查走内部探针）**

```markdown
## Deploy prod
1. Merge PR to main
2. Trigger `deploy-prod.yml` with tag
3. Verify readiness from container network:
   `docker compose exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz`
```

- [ ] **Step 2: 在审计清单中补 runbook 引用**

```markdown
- 证据路径示例：`docs/runbooks/deploy.md`、`docs/runbooks/rollback.md`
```

- [ ] **Step 3: 检查文档链接可解析**

Run: `rg "runbooks|audit-checklist|readyz" docs -n`  
Expected: 输出包含 deploy/rollback/backup-restore/audit-checklist 与内部健康检查引用

- [ ] **Step 4: Commit**

Run:
```bash
git add docs/runbooks docs/superpowers/specs/2026-05-11-rss-audit-checklist.md
git commit -m "docs: add operational runbooks and audit checklist linkage"
```

### Task 9: 生产前综合演练（staging -> prod）

**Files:**
- Modify: `docs/superpowers/specs/2026-05-11-rss-audit-checklist.md`
- Modify: `docs/runbooks/incident.md`
- Test: `end-to-end smoke and rollback`

- [ ] **Step 1: 在 staging 执行一次端到端演练**

Run:
```bash
bash infra/scripts/deploy.sh staging <tag>
curl -I https://staging-reader.<domain>
```
Expected: 200/302（取决于认证状态）

- [ ] **Step 2: 在 prod 演练一次可控回滚**

Run:
```bash
bash infra/scripts/deploy.sh prod <new-tag>
bash infra/scripts/rollback.sh prod <old-tag>
```
Expected: 回滚后内部健康检查通过（`readyz`）

- [ ] **Step 3: 填写审计清单并得出 Go/No-Go**

Run: `rg "PASS|FAIL|N/A|Go / No-Go" docs/superpowers/specs/2026-05-11-rss-audit-checklist.md -n`  
Expected: High 项全部 PASS 且证据齐全

- [ ] **Step 4: Commit**

Run:
```bash
git add docs/superpowers/specs/2026-05-11-rss-audit-checklist.md docs/runbooks/incident.md
git commit -m "chore: complete pre-release audit and rollback drill evidence"
```

---

## Self-Review

1. **Spec coverage:** 已覆盖认证、安全、数据模型、备份恢复、CI/CD、staging/prod 隔离与审计门槛。  
2. **Placeholder scan:** 仅保留必要骨架示例，无 `TODO/TBD`。  
3. **Type consistency:** `tenant_id/miniflux_entry_id/content_hash/model_version` 在任务中统一。  

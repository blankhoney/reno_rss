# DEPLOYMENT — AI Reader v0.4

> **历史规划文档，不可作为现行 runbook，也禁止按本文命令或 workflow 参数执行**：当前部署与 staging 边界以根目录 `SPEC-CICD.md`、`SPEC-CICD.zh-CN.md`、`docs/runbooks/deploy.md`、`docs/runbooks/rollback.md` 和现行 workflow 为准。当前三个手工 workflow 是 request-only；trusted orchestrator 尚未启用，request 不会自动部署或回滚。

> Compose 分层、Caddy 路由、GHCR 镜像、CI/CD、备份回滚。扩展现有 `infra/*` 与 `.github/workflows/ci.yml` 为 **web/api/worker 三镜像**。

## Current status (2026-08)

- **ARCHIVED / DO NOT EXECUTE:** this document is a historical v0.4 plan. Its old production environment, SSH, image, migration, and rollback steps are design history only.
- `deploy-staging.yml`, `deploy-prod.yml`, and `rollback.yml` remain request-only and upload `trusted-deploy-request/v1` data artifacts. `trusted-deploy.yml` now performs a verify-only provenance check from the default main checkout; it does not declare an environment, read deployment secrets, SSH, deploy, or roll back. Secret-bearing execution is not enabled, so a verified request still does not deploy or roll back an environment.
- Main branch protection, workflow-ID registration, Environment policies, and secret scope are not verified in this repository. Existing documentation records earlier control-plane observations, but those observations are not current API evidence. Do not treat the old `PASS` claims or execution examples below as current evidence.
- Use `SPEC-CICD.md`, `SPEC-CICD.zh-CN.md`, `docs/runbooks/deploy.md`, and `docs/runbooks/rollback.md` for the current boundary and inputs.

## 1. 仓库结构（原地重构 my_rss）

```
apps/{web,api,worker}/         三服务
infra/compose/                 base + local + staging + prod (+ backup)
infra/caddy/Caddyfile          公网入口
infra/scripts/                 deploy / smoke-test / backup / restore / rollback
docs/spec/                     本套 spec
.github/workflows/             ci.yml / deploy-staging.yml / deploy-prod.yml / rollback.yml
.github/scripts/               remote-deploy.sh 等
```

当前仓库仍是 `apps/reader-web` + `apps/scorer-worker`。M0 负责创建目标三服务结构；M0 前的 CI/compose 只能校验现状，不能假装三镜像已存在。

## 2. Compose 分层

- `docker-compose.base.yml`：共同服务定义（web/api/worker/postgres/miniflux），`profiles` 控制可选项。
- `docker-compose.local.yml`：本地开发（build 本地、暴露端口、热重载可选）。
- `docker-compose.staging.yml` / `prod.yml`：网络别名 + 环境差异（staging 开 demo landing）。
- `docker-compose.edge.yml`：单实例 Caddy（每 VPS 跑一次，staging/prod 共享 `app` 外部网络）。
- 网络：`app`（边缘可达：web/api/miniflux/authelia）、`data`（内部：postgres，仅后端可达）。
- compose 校验（CI 必过，含 `--profile worker`）：渲染 base、base+staging、base+prod 三组 config。

共享 `app` network 的硬约束：
- staging alias：`web-staging`、`api-staging`、`miniflux-staging`、`authelia-staging`（如启用 staging 外层）。
- prod alias：`web-prod`、`api-prod`、`miniflux-prod`、`authelia-prod`（如启用 prod 外层）。
- 禁止同时给 staging/prod 服务配置裸 `web`、`api`、`miniflux`、`authelia` alias。
- Caddy upstream 只能指向环境别名或 env var（例如 `AI_READER_API_UPSTREAM=api-staging:8000`）。

## 3. Caddy 路由（`infra/caddy/Caddyfile`）

```
ai-reader.{$DOMAIN} {
  @api path /api/*
  handle @api { reverse_proxy {$AI_READER_API_UPSTREAM} }
  handle /healthz { reverse_proxy {$AI_READER_API_UPSTREAM} }
  handle { reverse_proxy {$AI_READER_WEB_UPSTREAM} }   # / 与 /admin/* 都给 web
}
```
- prod env：`AI_READER_API_UPSTREAM=api-prod:8000`、`AI_READER_WEB_UPSTREAM=web-prod:3000`、`AI_READER_AUTH_UPSTREAM=authelia-prod:9091`（如启用）。
- staging env：`AI_READER_API_UPSTREAM=api-staging:8000`、`AI_READER_WEB_UPSTREAM=web-staging:3000`、`AI_READER_AUTH_UPSTREAM=authelia-staging:9091`（如启用）。
- staging（`staging-ai-reader.{$DOMAIN}`）：保留公开 demo landing 边界（`GET /` 空 query、`POST /api/auth/login`、`/_next/static/*`、`/favicon.ico` 公开；其余在 app auth readiness gate 通过前继续 Authelia 外层）。
- internal：miniflux/worker/postgres 不暴露公网。
- `/api/*` 由 `api` 自管鉴权（不依赖 Caddy forward-auth 保护业务）。

## 4. 镜像策略（GHCR）

```
ghcr.io/<owner>/ai-reader-web:sha-<short_sha>
ghcr.io/<owner>/ai-reader-api:sha-<short_sha>
ghcr.io/<owner>/ai-reader-worker:sha-<short_sha>
```
- staging 可用 branch/sha tag；**production 不用 `latest`**，用不可变 git SHA tag 或 digest。
- 部署 tag 必须匹配被部署的代码版本。

## 5. CI/CD 流水线（`ci.yml`）

| 阶段 | 步骤 |
|---|---|
| **PR** | lint（ruff/eslint）、typecheck、pytest（api+worker）、前端 `npm test`+`npm run build`、**Alembic migration check**（`upgrade head` 在干净库可重放 + 无未生成迁移）、**API schema check**（OpenAPI 可导出）、`docker build` check、compose config validate、Trivy（CRITICAL/HIGH 失败） |
| **main** | 跑测试 → build web/api/worker 镜像 → push GHCR → **deploy staging** → smoke test → mini benchmark（Mock，不产生 LLM 成本） |
| **production (ARCHIVED / DO NOT EXECUTE)** | 旧设计曾描述 `workflow_dispatch` + `production` 环境审批 → 备份 PostgreSQL → 拉精确 image SHA → migration dry-run/upgrade → `compose up` → healthcheck/smoke → 失败回滚；production environment 已有 required reviewer，但 deployment branch policy 未配置；当前 request-only `deploy-prod.yml` 不绑定或触发该 environment，trusted orchestrator 尚未启用。 |

- 自动 staging：main push 的 CI 路径；**fork PR 不部署、不读 secrets**。
- 失败可分类：checks / image build / SSH-secret / VPS dirty worktree / deploy / smoke。
- **ARCHIVED / DO NOT EXECUTE:** 旧远程部署设计曾让 `remote-deploy.sh` SSH 到 `VPS_APP_DIR`，校验 tracked worktree 干净，checkout `DEPLOY_SHA`，登录 GHCR，运行 `deploy.sh`。这段 dirty-worktree guard 只可由未来启用的 trusted orchestrator 复用；当前 request workflow 不执行它。

production DB 规则（历史设计；trusted orchestrator 启用并完成独立审批前不可执行）：
- migration 前必须 `backup.sh prod` 成功并输出备份 artifact 路径 + sha256。
- M0 clean cutover 可以创建新 schema/库，但必须保留旧库备份；禁止在未备份情况下 drop/overwrite。
- 常规迁移必须优先 expand/contract；若 migration 不可自动 downgrade，rollback runbook 必须写明从备份恢复。
- smoke 失败时，先回滚 image；若错误来自 schema 破坏，执行 restore runbook，不在 CI 里盲目二次迁移。

## 6. 部署脚本（`infra/scripts/`，ARCHIVED / DO NOT EXECUTE）

> 以下脚本接口是历史设计记录，不是当前手工 workflow 的调用方式。当前 request workflow 不执行这些脚本；未来 trusted orchestrator 是否复用它们，必须另行审核并验证。

- `deploy.sh <env> <tag>`：历史设计中的本地 build 或远程镜像模式；渲染 Caddy upstream env 与 Authelia 配置（如保留）；起 edge + 后端；幂等。
- `smoke-test.sh <env>`：可在已有独立部署证据后作为只读健康检查参考；校验容器、`GET /healthz`、`GET /api/healthz`、首页可达、鉴权边界和 staging demo landing；**不触发 LLM / 不改业务数据**。
- `backup.sh`：历史设计中的 `pg_dump -Fc` 业务库 + SHA256 校验，保留近 N 天。
- `restore.sh` / `rollback.sh`：历史设计中的从备份恢复 / 回滚旧 image tag 路径，不得直接执行。

## 7. 非功能要求（v0.4 §12 对齐）

- **安全**：secrets/cookies/SSH/API key/Basic Auth header 不打印。
- **可追溯（当前）**：request artifact 含完整 `deploy_sha`、immutable `image_tag` 和固定 schema；trusted orchestrator 执行后才记录 images、目标 URL 与 smoke 结果。
- **幂等（历史设计）**：trusted path 重复部署同 tag 应收敛、无需手动清理；当前 request-only workflow 不执行部署。
- **环境隔离**：staging 自动化不部署 prod。
- **auth 隔离**：staging deploy 不重建、不重启、不改写 prod Authelia/session/auth 配置；若 staging 使用 Authelia，必须是独立 `authelia-staging` 服务或显式只读外部服务。
- **成本控制**：自动 smoke/CI 不触发 LLM 评分或 Agent。

## 8. 环境变量（`.env.example` 占位，新增/调整）

- 通用：`DOMAIN`、PostgreSQL 各库密码与 URL。
- Miniflux：`MINIFLUX_API_BASE_URL` / `MINIFLUX_USERNAME` / `MINIFLUX_PASSWORD`（单服务账号）。
- LLM：`LLM_PROVIDER`（`minimax|mock`）、`MINIMAX_API_KEY` / `MINIMAX_BASE_URL` / `MINIMAX_MODEL`。
- api：`SCORING_DATABASE_URL`、`SESSION_COOKIE_DOMAIN`、`ALLOWED_ORIGINS`。
- worker：`WORKER_CONCURRENCY`、外部抓取 `EXTERNAL_CONTENT_PROVIDER` + key（可空）。
- staging demo：`DEMO_*`（如保留 demo 入口）。
- GHCR/部署（仅未来 trusted orchestrator，当前 request workflow 不读取）：`IMAGE_REGISTRY`、`IMAGE_TAG`、`VPS_HOST/USER/APP_DIR`、`VPS_SSH_KEY(_B64)`、`GHCR_USERNAME/TOKEN`。

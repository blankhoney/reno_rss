# RSS 系统设计文档（Miniflux v2）

日期：2026-05-11  
状态：已定稿（可进入实施计划）v3 hardening 同步  
适用阶段：当前单人使用，后续平滑演进到小团队/多租户

## 1. 目标与约束

### 1.1 目标
- 解决信息茧房问题：聚合大量信息源，支持后置筛选与分类。
- 以 Miniflux v2 为核心 RSS 引擎快速落地。
- 允许非实时处理：接收后分批评分，按时间窗复用数据输出。
- 为未来接入 OSINT 预留接口（当前不接入）。

### 1.2 已确认约束
- 部署区域：马来西亚 VPS（Debian，4C8G，约 70GB 存储）。
- 访问形态：跨城市协作者通过网页访问。
- 域名：已选用 Porkbun 购买域名。
- 缓存策略：允许缓存全文，保留 7 天。
- 当前功能定位：A 路线（个人/小团队阅读为主，AI 轻量排序/打标签）。
- 认证方式：本地账号 + Authelia 统一入口；首期使用用户名密码 + TOTP/Passkey。若必须邮箱魔法链接，需另选支持 Magic Link 的认证系统或自行开发。

## 2. 架构方案与结论

## 2.1 备选方案
1. **方案 1（推荐）**：Caddy + Authelia（本地用户 + TOTP/Passkey）+ Miniflux + PostgreSQL + 批处理评分服务  
2. 方案 2（最简）：Caddy + Miniflux 内置账号 + PostgreSQL + 批处理评分  
3. 方案 3（偏企业）：Nginx/Caddy + Keycloak + Miniflux + PostgreSQL + 队列

### 2.2 选型结论
固定采用 **方案 1**，在安全、复杂度与后续扩展之间最平衡。

## 3. 系统总体架构

## 3.1 主链路
`Browser -> Caddy(HTTPS, 单实例唯一入口) -> Authelia(认证) -> Miniflux -> PostgreSQL`

说明：同一台 VPS 上的 prod/staging 后端共享同一个 Caddy 实例（仅启动一次，独占 80/443），通过 Docker 网络别名（`miniflux-prod` / `miniflux-staging`、`authelia-prod` / `authelia-staging`）区分路由目标。

### 3.2 旁路链路（非实时评分）
`Scheduler/Cron -> Scoring Worker（内部循环，SCORER_INTERVAL_SECONDS） -> Miniflux API + Score Store`

### 3.3 未来 OSINT 预留
`Scoring Worker -> Export Adapter(JSON/Webhook/Queue)`  
当前仅定义接口，不连接 OSINT 系统。

## 4. 组件职责

- **Caddy**（`docker-compose.edge.yml`，project `myrss-edge`，独立于 prod/staging）
  - HTTPS 证书自动化（Let's Encrypt）
  - 反向代理与安全头
  - 入口统一收敛，仅暴露 443（80 仅做跳转）
  - **单实例启动一次**；prod/staging 后端通过 `myrss-app` 共享网络 + 别名路由，不重复绑定端口
- **Authelia**（`app` 网络，`_FILE` 方式注入 session secret 与 storage encryption key）
  - 本地用户目录（File）+ 多因素（TOTP/Passkey）
  - 会话管理与访问控制，`access_control.rules` 明确 allow 规则（`two_factor`）
  - 可作为 OIDC Provider（用于后续 Miniflux OIDC 登录）
  - `session.cookies` 明确 `domain` 与 `authelia_url`
- **Miniflux v2**（`app` + `data` 网络，`LISTEN_ADDR: 0.0.0.0:8080`，`BASE_URL` 指向外部域名）
  - 负责 RSS 抓取、阅读、分类与 API 输出
  - 不承载评分业务逻辑
  - **M1 阶段保留 Miniflux 本地账号**（用户需先过 Authelia 再登 Miniflux，双登录为预期行为，M2 再做 OIDC/Auth Proxy 集成）
- **PostgreSQL**（`data` 网络，不可从 `app`/`edge` 直接访问）
  - 通过 `docker-entrypoint-initdb.d` 初始化脚本创建 `miniflux` 与 `scoring` 专用用户及数据库
  - Miniflux 与 Worker 各使用最小权限账号连接
- **Scoring Worker**（`app` + `data` 网络，内部循环调度）
  - 从 Miniflux API 拉取最近条目并写入快照库（使用专用 API Key，不复用管理员账号）
  - 对未评分条目进行批处理，写入评分结果与作业状态
  - 调度方式：Worker 内部 `while True / sleep(SCORER_INTERVAL_SECONDS)`，MVP 最简可维护
  - 可选：根据评分结果触发 Miniflux 轻量动作（starred、read/unread、category 迁移）
- **Export Adapter（预留）**
  - 对外统一导出评分结果，减少后续系统耦合

### 4.1 认证演进路线

| 阶段 | 方案 | 说明 |
|---|---|---|
| M1 | Authelia File 用户 + 密码 + TOTP/Passkey | 最适合学习和快速上线；**用户需先通过 Authelia 认证，再登录 Miniflux 本地账号（双登录为预期行为，非 bug）** |
| M2 | Miniflux 接入 Authelia OIDC 或启用 `AUTH_PROXY_HEADER`（需配合 `TRUSTED_REVERSE_PROXY_NETWORKS`） | 降低双重登录与账号割裂 |
| M3 | 如确需 Magic Link，再评估 Authentik/PocketID/自研 | 不建议首发阶段引入 |

## 5. 数据流与策略

### 5.1 抓取与入库
- Miniflux 常规拉取订阅源并落库。
- 全文缓存保留 7 天。

### 5.2 批处理评分
- 周期执行（`SCORER_INTERVAL_SECONDS`，默认 3600 秒，建议起步 30-60 分钟）。
- 调度方式：Worker 内部 `while True / sleep`，不依赖外部 cron（MVP 最简）。
- 按“最近时间窗 + 未评分/需重评分”处理。
- 输出字段（`item_scores`，MVP 全量落库，便于后续接入真实 LLM 时无需改表）：
  - `score`（0-100）
  - `tags`（多标签 JSONB）
  - `reason`（可解释文本）
  - `model_version`、`model_provider`、`model_name`（便于回溯与切换模型）
  - `prompt_version`（prompt 迭代追踪）
  - `confidence`（置信度，可选）
  - `scoring_status`（`success` / `error`）
  - `error_message`（失败原因，可选）

### 5.3 复用与输出
- 支持同一时间窗数据重复利用，不依赖实时链路。
- 评分后可按规则筛选并作为后续信息补充输入。
- 允许误杀，以提升整体筛选效率。

## 6. 数据模型（逻辑层）

- `items_snapshot`
  - `id`
  - `tenant_id`
  - `miniflux_user_id`
  - `miniflux_entry_id`
  - `feed_id`
  - `feed_title`
  - `source_url`
  - `entry_url`
  - `title`
  - `summary`
  - `content_text`
  - `content_html`
  - `author`
  - `published_at`
  - `created_at`
  - `fetched_at`
  - `content_hash`
  - `language`
  - `retention_until`
- `item_scores`
  - `id`
  - `tenant_id`
  - `miniflux_entry_id`
  - `content_hash`
  - `score`
  - `tags`
  - `reason`
  - `confidence`
  - `model_provider`
  - `model_name`
  - `model_version`
  - `prompt_version`
  - `scored_at`
  - `scoring_status`
  - `error_message`
- `scoring_jobs`
  - `id`
  - `tenant_id`
  - `window_start`
  - `window_end`
  - `status`
  - `total_count`
  - `success_count`
  - `failed_count`
  - `skipped_count`
  - `started_at`
  - `finished_at`
  - `duration_ms`
  - `error_summary`
- `feed_health`
  - `id`
  - `tenant_id`
  - `feed_id`
  - `feed_url`
  - `last_success_at`
  - `last_error_at`
  - `error_count`
  - `last_error_message`
  - `disabled_reason`
- `export_cursor`
  - `id`
  - `tenant_id`
  - `target_name`
  - `last_exported_score_id`
  - `last_exported_at`

说明：`tenant_id`、`miniflux_entry_id`、`content_hash`、`fetched_at`、`retention_until` 为首期必备字段，用于幂等重跑、内容变化检测、重评与故障恢复。

## 7. 安全设计基线

### 7.1 主机层
- 仅开放必要端口（22/80/443；可限制 22 来源）。
- SSH 仅密钥登录，禁用 root 直登。
- SSH 禁用密码登录。
- 启用自动安全更新与 fail2ban。

### 7.2 网关与认证层
- 全站强制 HTTPS。
- Caddy 设置 HSTS、X-Frame-Options、X-Content-Type-Options。
- 所有 Miniflux 访问必须经 Authelia 认证（`default_policy: deny` + 明确 allow rules）。
- 设置会话过期和管理员应急账号策略。
- Authelia secret 使用 `_FILE` 环境变量方式加载（`AUTHELIA_SESSION_SECRET_FILE`、`AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE`），避免明文写入配置或 compose 文件。
- `storage.encryption_key` 为 Authelia 必填项（最小长度 20，推荐 64+ 随机字符），须通过环境变量注入，不硬编码在 `configuration.yml`。
- Authelia `session.cookies` 必须明确 `domain` 与 `authelia_url`，确保 session 覆盖正确域名。
- 健康检查走容器内部探针（`docker compose exec miniflux wget -qO- http://127.0.0.1:8080/readyz`），不依赖经过 Authelia 的外部 URL。

### 7.3 数据层与网络边界（三层）
- **网络分层**：
  - `edge`（`myrss-edge` 共享网络）：Caddy 与各后端服务通信
  - `app`：Authelia、Miniflux、Scoring Worker 互联
  - `data`：Miniflux、Scoring Worker 与 PostgreSQL 互联
  - PostgreSQL 仅存在于 `data` 网络，Caddy 不可直接访问数据库
- PostgreSQL 不对公网暴露，且不在 `app`/`edge` 网络内。
- PostgreSQL 通过 `docker-entrypoint-initdb.d` 初始化脚本创建 `miniflux` 与 `scoring` 专用账号；不使用 postgres 超级用户连接业务库。
- 评分服务仅使用最小权限访问必要数据/API。
- Worker 使用专用低权限 Miniflux API Key（在 Miniflux 管理界面创建，记录轮换步骤，不复用管理员密钥，不入库）。
- 日志脱敏：不记录全文、API Key、邮箱验证码、Cookie、Authorization 头。
- 所有 secrets 不进入 Git 仓库，使用 `.env`（本地）+ 服务器私有 secret 文件或 Docker secrets。

## 8. 错误处理与恢复策略

### 8.1 错误处理
- 抓取失败按阈值标记为降级源，降低抓取频率。
- 评分任务单条失败不影响整批；支持幂等重跑。
- 邮件登录失败给出明确反馈，并保留管理员应急入口。

### 8.2 备份与恢复
- PostgreSQL（MVP）：每日逻辑备份（`pg_dump -Fc miniflux`、`pg_dump -Fc scoring`）。
- 配置文件：Caddy/Authelia/Worker/compose 每日快照。
- 保留策略：本地 7 天 + 异地 30 天。
- 恢复目标：RPO <= 24h，RTO <= 2h。
- 每月至少一次恢复演练。
- 中长期：若需更低 RPO，再引入 WAL 归档与 PITR。

### 8.3 月度恢复演练验收步骤
1. 新建临时数据库。
2. 从备份恢复 miniflux 与 scoring。
3. 启动临时 Miniflux 并验证登录。
4. 检查用户、订阅源、最近条目是否完整。
5. 检查评分数据是否完整。
6. 验证 Worker 能从 export/scoring cursor 继续处理。
7. 删除临时环境并记录演练结果。

## 9. CI/CD 与 Git 版本管理（固定方案 A）

### 9.1 Git 工作流
- 分支：
  - `main`：生产
  - `develop`：集成/预发
  - `feature/*`、`fix/*`、`hotfix/*`
- 规则：
  - 禁止直接推送 `main/develop`
  - 通过 PR 合并
  - 采用 SemVer（`vMAJOR.MINOR.PATCH`）

### 9.2 GitHub Actions 工作流
1. `ci.yml`（PR 必跑）
   - lint/test/build/security scan
2. `deploy-staging.yml`（push 到 develop）
   - 自动部署 staging 并做健康检查
3. `deploy-prod.yml`（tag 或手动触发）
   - 部署生产并做健康检查
4. `rollback.yml`（手动）
   - 指定 tag 回滚并验证

### 9.3 自动 Review 与门禁
- 启用 GitHub PR Review + Cursor/Codex 自动 review。
- 关键路径（`infra/**`、`apps/scorer-worker/**`、`.github/workflows/**`）配置 `CODEOWNERS`。
- **CODEOWNERS 本身不强制 review**，必须在 branch protection / ruleset 中启用 "Require review from Code Owners" 才生效。
- `main`：require PR、require status checks、require Code Owner review、block force push、block deletion。
- `develop`：require PR、require status checks。
- `deploy-prod.yml` 的 deploy job 必须配置 `environment: name: production`，启用 GitHub Environment 保护规则（可配置手动审批与分支限制）。
- Trivy action 版本不低于 `0.35.0`（低于该版本的 tag 存在供应链安全风险）。

## 10. 部署与环境策略

- 单机双环境（同一 VPS）：
  - `staging`：预发验证
  - `prod`：正式服务
- **Caddy 单实例原则**：同一台 VPS 仅启动一个 Caddy 容器（`myrss-edge` project），独占 80/443；prod/staging 后端服务均使用不同 compose project（`myrss-prod` / `myrss-staging`），通过 `myrss-edge` 共享网络 + 别名路由，不各自启动 Caddy。
- 环境隔离要求：
  - staging/prod 使用不同数据库（用户、数据库名均隔离）
  - staging/prod 使用不同 compose project name（`myrss-prod` / `myrss-staging`）
  - staging/prod 通过不同网络别名连接同一 Caddy
  - staging 限制 RSS 源数量与缓存规模
  - 默认仅备份 prod（staging 按需）
- 推荐域名规划：
  - `reader.<domain>`：阅读入口
  - `auth.<domain>`：认证入口
  - `api.<domain>`：后续评分/导出接口（预留）
  - `staging-reader.<domain>`：staging 阅读入口
  - `staging-auth.<domain>`：staging 认证入口
  - `staging-api.<domain>`：staging 评分/导出接口

## 11. 迭代路线图（建议）

- **M1（第 1-3 天）**：Miniflux + Caddy + Authelia + PostgreSQL 上线
- **M2（第 4-7 天）**：评分 Worker（时间窗处理 + 结果落库）
- **M3（第 8-10 天）**：缓存清理 + 备份与恢复演练
- **M4（第 11-14 天）**：CI/CD 与发布门禁全启用

## 12. 非目标（当前阶段不做）

- 不做实时流式评分与实时推送。
- 不接入正式 OSINT 系统。
- 不引入重型企业 IdP（如 Keycloak）作为首发依赖。

## 13. 验收标准（最小闭环）

- 异地协作者可通过 HTTPS 网页稳定访问。
- 本地账号 + TOTP/Passkey 登录流程稳定，未登录用户无法访问阅读入口。
- RSS 抓取 + 批处理评分 + 分类筛选完整可用。
- 7 天缓存策略生效，备份恢复可演练成功。
- PR 到发布链路可重复执行并支持回滚。

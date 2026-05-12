# 学习笔记（my_rss 项目）

## 怎么用这份笔记

- **追问 / 复习**：另开 Cursor Chat，`@docs/learning-notes.md` 后提问。
- **想更偏「讲课」**：同一条消息里再 `@docs/teaching-session.md`（见 `.cursor/rules/teaching-session.mdc`）。
- **与计划对照**：带编号的工程 Task 以 `docs/superpowers/plans/2026-05-11-rss-mvp-implementation-plan.md` 为准（Task 4=TDD、Task 5=幂等写入等）；本文件在编号旁会注明与计划的对应关系。

---

## 学习路径速览

| 顺序 | 笔记章节 | 状态 | 说明 |
|:---:|:---|:---|:---|
| 1 | Task 1：仓库骨架与 Compose 分层 | 已记录 | 仓库内 compose 实际路径见该节 |
| 2 | Task 2：Caddy + Authelia 入口认证 | 已记录 | 含 PG init 脚本创建 |
| 3 | Task 3：PostgreSQL + Miniflux | 并入 Task 2 | 初始化脚本已在 Task 2 落地 |
| 4 | 补充：首次部署前置（VPS / DNS / Secret） | 已记录 | 上机前动手清单；**编号≠计划 Task 4** |
| 5 | 首次部署排障记录 | 已记录 | 真机常见问题：`--env-file`、DOMAIN、安全组、Authelia 等 |
| 6 | Task 6：运维脚本 | 已记录 | deploy / rollback / backup / restore |
| 7 | Task 4：Scorer Worker 骨架（TDD） | 已记录 | 与计划 **Task 4** 对齐；`apps/scorer-worker` |
| 8 | Task 5：评分库 schema 与幂等写入 | 已记录 | 与计划 **Task 5** 对齐；SQL + repository 测试 |
| 9 | Task 7：GitHub Actions CI/CD | 已记录 | 与计划 **Task 7** 对齐；workflows + CODEOWNERS |
| 10 | Task 8 + 9：Runbooks 与演练清单 | 已记录 | `docs/runbooks/`；与计划 **Task 8/9** 对齐 |
| 11 | 设计：AI 阅读工作台前端 | 已记录 | 新前端主入口，Miniflux 退到 RSS 后端 |

### 下一步可以学什么（新开 session 时从这里选）

1. **若优先「真机跑通」**：按「补充：首次部署前置」起 edge + 环境；遇错对照「首次部署排障记录」；再对照 `infra/caddy/Caddyfile` 理解路由。
2. **若巩固 Worker 与数据层**：按顺序读 **Task 4**（TDD 与 payload）→ **Task 5**（表结构、`ON CONFLICT`、Mock 测试）。
3. **若巩固发布与事故响应**：读 **Task 7**（CI、审批、Trivy）→ **Task 8+9**（runbook、演练）；与 **Task 6** 脚本、`docs/runbooks/` 交叉对照。
4. **若开始做阅读体验**：先读「设计：AI 阅读工作台前端」，理解为什么不改 Miniflux，而是新增 `reader-web`。

---

## Task 1：仓库骨架与 Compose 分层

> 与计划 **Task 1** 对齐。

### 做了什么

- 创建了 `.gitignore`、`.env.example`
- 创建了四份 Compose（仓库内实际路径）：
  - `infra/compose/docker-compose.edge.yml`
  - `infra/compose/docker-compose.base.yml`
  - `infra/compose/docker-compose.prod.yml`
  - `infra/compose/docker-compose.staging.yml`

### 关键概念

**为什么 .env 不能进 Git**
Git 的历史是永久的。即使你后来删掉了 .env，`git log` 里那条提交永远存在，
任何人 clone 后都能用 `git show` 找到密码。`.gitignore` 是第一道防线。

**Compose 文件为什么要分层（base / prod / staging）**
prod 和 staging 结构相同，只有别名和少数变量不同。
`docker-compose.base.yml` 定义共同结构，prod/staging 只覆盖差异，
这样修改公共配置只需改一个地方。

**为什么 Caddy 要单独一个 edge compose**
一台 VPS 的 80/443 端口只有一组。
如果 prod 和 staging 各自带一个 Caddy，第二个启动时会报「端口占用」。
解决方案：Caddy 独立启动一次（例如 project: `myrss-edge`），
prod/staging 后端通过 Docker 网络别名告诉 Caddy 自己在哪里。

**三层网络（edge → app → data）**

- app 网络：Caddy ↔ Authelia ↔ Miniflux ↔ Worker 互通
- data 网络：Miniflux ↔ Worker ↔ PostgreSQL 互通
- Caddy 不在 data 网络 → 网关永远访问不到数据库

**网络别名（aliases）**
Caddyfile 里写死了 `miniflux-prod` 和 `miniflux-staging` 等名字。
prod 给 Miniflux 容器设置 `aliases: [miniflux-prod]`，
staging 设置 `aliases: [miniflux-staging]`。
这样同一个 Caddy 就能区分两套后端。

### 可以在学习 session 里追问的问题

- Docker 网络是怎么工作的？容器之间怎么找到对方？
- `external: true` 是什么意思？
- `docker compose -p` 的 project name 有什么用？
- `restart: unless-stopped` 和 `always` 有什么区别？
- `.env.example` 里的连接串格式 `postgres://user:pass@host:port/db` 怎么读？

---

## Task 2：Caddy + Authelia 入口认证

> 与计划 **Task 2** 对齐。

### 做了什么

- 创建了 `infra/caddy/Caddyfile`：四条站点块（prod：`reader` / `auth`；staging：`staging-reader` / `staging-auth`），与 Porkbun 上 **四条 A 记录**（同主机名前缀）一一对应
- 创建了 `infra/authelia/configuration.yml`：认证网关规则手册
- 创建了 `infra/authelia/users_database.yml`：本地用户模板（密码用 argon2id 哈希）
- 创建了 `infra/postgres/init/001-create-databases.sh`：PG 初始化脚本（与下方 Task 3 说明重叠，见 Task 3 节）

### 关键概念

**forward_auth 是什么**
每次请求到达 reader.<domain> 时，Caddy 先把请求「转问」Authelia：
「这个用户登录了吗？」Authelia 说 OK（HTTP 200）→ 请求继续到 Miniflux；
Authelia 说未登录（401/302）→ 浏览器被重定向到登录页。
整个过程对用户透明，就像在进门前先刷卡。

**为什么 auth.<domain> 不需要 forward_auth**
auth.<domain> 就是登录页本身（Authelia），如果登录页也要先登录才能进，就死循环了。

**access_control default_policy: deny + rules**
只写 `default_policy: deny` 不写 rules，相当于门卫说「所有人都不能进」。
rules 是例外列表：reader.<domain> 的用户只要通过二因子认证就放行。

**argon2id 哈希**
密码存储不能用明文，哈希是单向函数（无法从哈希反推密码）。
argon2id 的特点是「故意很慢」——暴力穷举需要消耗大量内存和时间，
即使数据库泄露，破解成本也极高。

**PostgreSQL 初始化脚本只跑一次**
Docker PG 镜像的规则：`/docker-entrypoint-initdb.d/` 里的脚本
只在数据目录（`/var/lib/postgresql/data`）为空时执行。
第一次启动 → 创建用户和数据库；之后重启 → 跳过，不会重复执行。
如果想重新初始化，必须先删除数据 volume（`docker volume rm ...`），会丢数据！

**storage.encryption_key 为什么重要**
Authelia 把 2FA 设备注册信息加密存在 SQLite 里，用这个 key 加密。
key 丢失 = 数据库变成乱码 = 所有用户要重新注册 2FA。
所以它和密码一样：永远不进 Git，妥善备份。

### 真实部署前必须做的事

1. 生成 argon2id 密码哈希，替换 `users_database.yml` 里的占位符
2. 在服务器创建 `/opt/myrss/secrets/` 目录，写入两个 secret 文件
3. 把 `DOMAIN` 填写为你真实域名
4. 把 Authelia `configuration.yml` 里的 `example.com` 替换为真实域名

### 可以在学习 session 里追问的问题

- HTTP forward_auth 的完整流程是什么？Authelia 和 Caddy 之间发了几次请求？
- argon2id 和 bcrypt 有什么区别？为什么现在推荐 argon2id？
- TOTP 是怎么工作的？为什么扫码后不需要网络也能生成验证码？
- Docker secrets 和环境变量有什么区别？为什么用 _FILE 方式更安全？
- Authelia SQLite 和真实数据库（PostgreSQL）有什么区别？什么时候需要换 PG？

---

## 设计：AI 阅读工作台前端

### 做了什么

确认了新前端的产品边界：不改 Miniflux 源码，而是新增一个 AI 阅读工作台作为日常主入口。Miniflux 继续负责 RSS 抓取、订阅源、分类、已读/未读和收藏；新前端负责多维评分排序、模块化阅读、站内阅读、专注模式、稍后读和当前文章 Agent。

### 关键概念

**为什么不直接改 Miniflux 页面**
Miniflux 的价值是稳定 RSS 后端，不是复杂阅读体验。直接改它的页面会增加升级维护成本；新增前端可以自由设计阅读界面，同时继续复用 Miniflux 的稳定 API。

**AI 阅读工作台**
它不是普通 RSS 列表，而是按分数、模块、标签和阅读状态组织信息的工作台。用户先通过分数和模块筛选，再决定站内阅读、稍后读、收藏或打开原文。

**多维评分**
单一总分只能告诉你“总体值得不值得看”，但不能说明“为什么值得”。多维分数把文章拆成重要性、实用性、时效性、深度、技术价值、商业价值和趋势价值，前端可以按不同模块使用不同排序规则。

**当前文章 Agent**
第一版 Agent 只围绕当前文章回答，不做全库问答。它支持流式输出、快捷按钮、自由追问、选中文字作为引用，并在需要事实查证时联网搜索，减少弱模型胡编。

**状态边界**
已读、未读、收藏优先复用 Miniflux；稍后读、阅读历史、个人笔记这类 Miniflux 没有的状态放进 reader 自己的表。这样既不污染 Miniflux，又方便以后扩展。

### 可以在学习 session 里追问的问题

- 为什么“新增前端 + 复用 Miniflux API”比 fork Miniflux 更容易维护？
- `tenant_id` 和 `miniflux_user_id` 为什么对未来多用户很重要？
- 多维评分为什么适合放进 JSONB，而不是一开始就拆成很多列？
- SSE / streaming response 为什么能改善 Agent 体验？
- 什么情况下 Agent 必须联网搜索，什么情况下只读当前文章就够？

---

## 计划：AI 阅读工作台实现拆解

### 做了什么

把 AI 阅读工作台拆成可逐步验证的 implementation plan：先升级评分 schema 和多维评分，再建立 reader-web 的数据契约，最后实现页面、状态操作、Agent、部署配置和验证。

### 关键概念

**为什么数据契约先行**
前端页面依赖文章、分数、状态和模块排序。如果先画 UI，再改评分结构，很容易返工。先把 `dimension_scores`、`reader_entry_states`、文章 API 和类型定义清楚，UI 才有稳定输入。

**为什么每个任务都要能测试和提交**
这个功能跨度大，包含 Python worker、Next.js、PostgreSQL、Docker Compose 和 Caddy。小任务 + 测试 + 提交可以让错误停在局部，避免最后一次性排查所有问题。

**为什么 Agent 放到后段实现**
Agent 依赖文章正文、评分理由、选中文字和流式 API。只有阅读页面与文章数据稳定后，Agent 的上下文才可靠。

### 可以在学习 session 里追问的问题

- 什么叫“数据契约”？为什么它比 UI 更早确定？
- 为什么大型功能要拆成多个可提交任务？
- TDD 在前端 API 和数据库 schema 里怎么用？

---

## Task：Scorer 多维分 + Reader 数据契约（实施记录）

### 做了什么

- 实施计划 Task 1：`item_scores` 增加 `dimension_scores`（JSONB），`upsert_score` 可持久化多维分；有 `SCORING_DATABASE_URL` 时集成测试会跑 `test_upsert_score_persists_dimension_scores`。
- Task 2：评分 prompt 为 `rss-score-v2`，LLM 输出 `overall` 与七个维度；若 JSON 仍是旧版只有 `score`，未给出的维度会回退到 overall，避免前端看到一堆 0；baseline 路径同样带上 `dimension_scores`。
- Task 3： scoring 库增加 `reader_entry_states`；`apps/reader-web` 初构，`toArticleScore` 与 `setReadLaterSql` 有 Node 单测。

### 关键概念

**向后兼容的解析**  
旧响应可能只有总分字段。解析时用 `overall` 或 `score` 作为 headline，并把缺失的各维分对齐到该值，兼容测试与线上历史数据。

**读者状态与 Miniflux 分离**  
已读、收藏可由 Miniflux 管理；「稍后读」用 scoring 库的 `reader_entry_states`，不塞进 Miniflux 的状态机。

### 可以在学习 session 里追问的问题

- JSONB 存多维分与「每维一列」各有什么取舍？
- 为什么 reader-web 要有 TypeScript 里的 `repository.ts`，同时 worker 还有 Python `repository.py`？

---

## Task 3：PostgreSQL 初始化 + Miniflux 配置

> 与计划 **Task 3** 对齐（实现计划里仍有更细的 Miniflux/Worker 配置与自测问题）。

**当前仓库状态**：`infra/postgres/init/001-create-databases.sh` 已在 Task 2 阶段创建；Compose 中 Miniflux 与数据库连接串等以 `docker-compose.base.yml` 与 `.env.example` 为准。后续若单独扩展「仅 Task 3」的实验（例如只起 DB + Miniflux），可在此节追加「做了什么 / 关键概念」。

---

## 补充：首次部署前置（VPS / DNS / Secret）

> **注意**：本节是 **上机动手顺序**，**不是**实现计划里的「Task 4（TDD）」。计划 Task 4 见 `docs/superpowers/plans/...` 表格。

### 做了什么

- 在 VPS 创建 `/opt/myrss/secrets/` 目录，写入两个 Authelia secret 文件
- 在 Porkbun（或当前域名的权威 DNS）配置 **四条 A 记录**：`reader`、`auth`、`staging-reader`、`staging-auth` 的 **Host** 填这些前缀，**Answer** 均为 VPS 公网 IPv4（与 `Caddyfile` 中域名一致）
- `git clone` 仓库到 `/opt/myrss/app`，复制 `.env.example` 为 `.env` 并填写真实值
- 用 Docker 生成 argon2id 密码哈希，写入 `users_database.yml`

### 关键概念

**为什么 secret 用文件而不是环境变量**
环境变量在 Linux 下可以被同主机上其他进程读取（`/proc/<pid>/environ`）。
文件可以设置权限 `chmod 600`，只有特定用户可读，安全边界更清晰。
Docker secrets（`--secret` 参数）把文件挂载到容器内 `/run/secrets/`，
应用只在需要时读取，读完就可以关闭文件句柄。

**为什么 DNS 要在启动 Caddy 前就配好**
Caddy 启动时立即向 Let's Encrypt 发起证书申请（ACME HTTP-01 challenge）。
Let's Encrypt 会用 HTTP 访问你的域名来验证你拥有它。
如果 DNS 还没指向你的 VPS，Let's Encrypt 访问不到，申请失败。
Caddy 会重试，但每次失败都消耗 Let's Encrypt 的速率限额
（同一域名每周最多失败 5 次，超过需等一周）。

**argon2id 哈希是怎么生成的**

```bash
docker run --rm authelia/authelia:latest \
  authelia crypto hash generate argon2 --password 'YOUR_PASSWORD'
```

输出格式：`$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`

- `m=65536`：使用 64MB 内存计算（让暴力破解更贵）
- `t=3`：迭代 3 次
- `p=4`：4 线程并行
这些参数让每次哈希计算需要约 0.5 秒 + 64MB 内存，
攻击者暴力穷举 100 亿个密码需要几十年和大量内存。

**openssl rand -hex 32 生成了什么**
`openssl rand` 从系统安全随机源（`/dev/urandom`）读取随机字节。
`-hex 32` 表示 32 字节，输出为 64 个十六进制字符。
这比任何人工想的密码都强，不可预测，不可暴力破解。

**.env 里两个密码必须一致的地方**
`POSTGRES_MINIFLUX_PASSWORD` 和 `MINIFLUX_DATABASE_URL` 里的密码必须完全相同。
前者是 PostgreSQL 初始化时设置的密码，后者是 Miniflux 连接时用的密码。
如果不一致，Miniflux 启动时会报 `password authentication failed`。

### 可以在学习 session 里追问的问题

- ACME HTTP-01 challenge 是怎么工作的？Let's Encrypt 如何证明你拥有域名？
- `/proc/<pid>/environ` 是什么？为什么环境变量可以被其他进程读到？
- `chmod 700` 和 `chmod 600` 有什么区别？
- argon2id 和 argon2i、argon2d 有什么区别？为什么选 argon2id？
- DNS TTL 设 300 是什么意思？为什么调试阶段设小一点？

---

## Task 6：运维脚本（deploy / rollback / backup / restore）

> 与计划 **Task 6** 对齐。

### 做了什么

- `deploy.sh`：先确保 edge 网络存在，启动 Caddy，再启动对应环境后端
- `rollback.sh`：复用 deploy.sh，用旧 tag 重新部署即为回滚
- `backup.sh`：docker exec 进 PG 容器跑 pg_dump，生成校验和
- `restore.sh`：验证校验和 → 停服 → pg_restore → 重启服务

### 关键概念

**为什么回滚 = 重新 deploy 旧版本**
容器是无状态的，镜像 tag 决定版本。
「回滚」不需要特殊操作，用旧 tag 跑一次 deploy 就完成了。
数据库数据不受影响（volume 独立于容器生命周期）。

**pg_dump -Fc 是什么格式**
`-Fc` 是 PostgreSQL 的「自定义格式」（custom format），自带压缩。
比 SQL 文本格式小很多，也只能用 `pg_restore` 恢复（不能直接 psql < dump）。

**为什么备份要生成 sha256**
备份文件可能在传输、存储过程中损坏（bit rot、磁盘错误）。
sha256 是一种指纹，文件内容变了指纹就变。
恢复前 `sha256sum --check checksums.txt` 能立刻发现文件损坏，
避免用坏的备份恢复后才发现数据丢失。

**restore.sh 为什么要先停服**
如果 Miniflux 还在写数据库，恢复过程中可能产生写冲突，
导致恢复后数据不一致。先停服再恢复，是标准做法。

### 可以在学习 session 里追问的问题

- `set -euo pipefail` 四个选项各是什么意思？
- `docker exec -i` 的 `-i` 是什么？为什么 backup 用 `exec`，restore 用 `exec -i`？
- pg_dump 和 pg_dumpall 有什么区别？
- 为什么 rollback 不需要专门备份？什么情况下回滚会有风险？

---

## 首次部署排障记录（重要学习材料）

### 遇到的问题与解法

**问题 1：.env 中文注释导致 Docker Compose 解析失败**
`--env-file` 不支持中文注释，报 `unexpected character "#"`。
解法：`grep -v '^#' .env | grep -v '^[[:space:]]*$' > /tmp/env.clean && mv /tmp/env.clean .env`
根治：`.env.example` 改为纯 ASCII 注释。

**问题 2：Caddy 报 `staging-reader.`（域名为空）**
原因：`--env-file` 只给 Docker Compose 自身做变量替换，不会注入容器环境。
Caddyfile 里 `{$DOMAIN}` 读取的是容器内的环境变量，必须在 compose 里显式声明 `environment: DOMAIN: ${DOMAIN}`。

**问题 3：Authelia `{{ env "DOMAIN" }}` 模板不生效**
错误：模板表达式被当字面量解析，导致域名校验失败。
解法：放弃 Authelia 模板引擎，改用 `envsubst`。
`deploy.sh` 在 docker compose 前运行：
`envsubst < configuration.yml.tmpl > configuration.yml`

**问题 4：Authelia 报 `jwt_secret` 缺失**
原因：禁用密码重置的正确位置是 `authentication_backend.password_reset.disable: true`，
而非 `identity_validation.reset_password.disable`（该 key 不存在）。

**问题 5：云安全组未开放 80/443**
iptables 显示 ACCEPT 但仍无法从外部访问。
原因：云平台安全组独立于系统 iptables，是云平台层面的防火墙，在流量抵达 VM 之前就过滤。
解法：在控制台安全组规则里添加 TCP 80/443 入站。

**问题 6：验证码速率限制**
多次点击"发送验证码"触发 Authelia rate limit。
解法：`docker restart myrss-prod-authelia-1` 清除内存中的限制，之后只点一次再读文件。

### 关键概念

**envsubst 是什么**
`envsubst` 是 Linux 标准工具，读取文本文件，把 `${VAR}` 替换为当前环境变量值，输出新文件。
不需要任何编程语言，是处理配置模板的最简方案。

**云安全组 vs iptables**
iptables：操作系统内核防火墙，ACCEPT 表示系统不拦截。
安全组：云平台在虚拟网络层面的防火墙，在流量到达 VM 之前就过滤。
两者独立，必须都放行才能访问。

**Authelia 二步验证注册流程（MVP）**
1. 用户名密码登录（第一因子）
2. 注册 TOTP 前需 session elevation（身份二次确认）
3. Authelia 发"邮件"→ MVP 下写入 /config/notification.txt
4. 填入验证码后扫 TOTP 二维码完成注册
5. 下次登录：用户名密码 + TOTP 验证码

**filesystem notifier**
`notifier.filesystem` 把所有"邮件"写入容器内文件而非真正发送。
查看：`docker exec myrss-prod-authelia-1 cat /config/notification.txt`
适合 MVP/测试，生产阶段换成 SMTP。

### 可以在学习 session 里追问的问题
- Docker Compose `--env-file` 和 `environment:` 的区别？变量如何流向容器？
- Let's Encrypt 速率限制是什么？申请失败太多次会怎样？
- Authelia rate limiting 基于 IP 还是账号？能不能自定义配置？
- TOTP 和短信验证码有什么区别？为什么 TOTP 更安全？
- 云安全组和防火墙哪个先生效？流量的完整路径是什么？

---

## Task 4: Scorer Worker 骨架（TDD 最小闭环）

### 做了什么
用 TDD 流程创建了评分 Worker 的最小可运行版本：
1. 先写 `tests/test_scoring.py`（含 5 个测试，覆盖 payload 结构、类型、边界条件）
2. 运行测试 → 确认 FAIL（`ModuleNotFoundError`）
3. 实现 `src/scoring.py`（基于内容长度的启发式评分）
4. 运行测试 → 全部 PASS

还创建了：
- `src/miniflux_client.py`：通过 Miniflux REST API 拉取条目
- `src/main.py`：调度主循环（fetch → snapshot → score → sleep）
- `Dockerfile`：Python 3.12-slim 镜像
- `pyproject.toml`：项目依赖与工具配置

### 为什么先写失败测试（TDD）
先写 test 能在实现前明确接口契约（payload 的 key 必须是哪些）。
如果先写代码，测试往往会迁就实现细节，掩盖设计问题。
"先见证失败"确保测试本身是有效的，而不是一个永远为绿的摆设。

### 评分 Worker 的 payload 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | int (0-100) | 基于内容长度的得分（后续换 LLM） |
| `tags` | list[str] | 从标题提取的关键词 |
| `reason` | str | 得分理由（length= + hash=） |
| `model_version` | str | 模型版本号 |
| `model_provider` | str | 提供方（baseline / openai 等） |
| `model_name` | str | 模型名称 |
| `prompt_version` | str | Prompt 版本 |
| `confidence` | float | 置信度 0-1 |
| `scoring_status` | str | success / error |
| `error_message` | str / None | 错误信息 |

### 如何在新服务器复现
```bash
cd apps/scorer-worker
pip install -e ".[dev]"
pytest tests/test_scoring.py -v   # 应该 5 passed
```

### 可以追问的问题
- `pyproject.toml` 和 `requirements.txt` 有什么区别？什么时候用哪个？
- `[build-system]` 里的 `build-backend` 是做什么的？
- TDD 的 Red-Green-Refactor 循环是什么意思？

---

## Task 5: 评分库 schema 与幂等写入

### 做了什么
创建了评分数据库的完整 schema 和 repository 层：
1. `sql/001_init_scoring.sql`：5 张表，全部 `CREATE TABLE IF NOT EXISTS`
2. `src/repository.py`：`upsert_snapshot` + `upsert_score`，使用 `ON CONFLICT … DO UPDATE`
3. `tests/test_repository.py`：6 个测试，用 Mock DB 连接验证 SQL 和提交行为

### 5 张表的职责

| 表 | 职责 |
|----|------|
| `items_snapshot` | 从 Miniflux 拉取的条目快照（去重键：tenant + entry_id） |
| `item_scores` | 评分结果（去重键：tenant + entry_id + content_hash + model_version） |
| `scoring_jobs` | 批次运行记录（审计 / 幂等） |
| `export_cursor` | 增量导出游标（避免重复处理） |
| `feed_health` | 每个 Feed 的健康状态追踪 |

### 为什么用 ON CONFLICT + DO UPDATE（Upsert）
如果同一条 RSS 条目被评分 3 次（网络重试、Worker 重启等），
普通 INSERT 会报唯一约束冲突并中断；
ON CONFLICT DO UPDATE 会用最新值覆盖，`scored_at` 更新为 NOW()。
结果：数据库里只有一条记录，且是最新评分，不产生脏数据。

### 为什么用 Mock 而不是真实 DB 做测试
单元测试不应依赖外部服务（PostgreSQL）。
用 `unittest.mock.MagicMock` 模拟连接和游标，验证：
- SQL 是否被调用了（execute 调用次数）
- SQL 是否包含 ON CONFLICT 子句
- tags 是否被序列化成 JSON 字符串
这类测试速度快、无副作用，可在 CI 里无 DB 运行。

### 如何在新服务器复现
```bash
cd apps/scorer-worker
pytest tests/test_repository.py -v   # 应该 6 passed
```

---

## Task 7: GitHub Actions CI/CD

### 做了什么
创建了 4 个 workflow + CODEOWNERS + PR 模板：
- `ci.yml`：PR 时触发，依次 ruff lint → pytest → compose validate → Trivy 扫描
- `deploy-staging.yml`：push develop 分支自动部署 staging
- `deploy-prod.yml`：手动触发，需通过 `production` Environment 审批
- `rollback.yml`：手动触发，支持 staging/prod 双环境回滚

### `environment: production` 的作用
GitHub Actions Environment 是一个保护层：
可配置"需要指定人员批准才能运行"，把手动部署变成需要审批的流程。
防止误触 workflow_dispatch 直接推 prod。

### CODEOWNERS 的作用
列出高风险目录的 owner（`infra/`, `.github/workflows/`, `apps/scorer-worker/`）。
配合分支保护的"Require review from Code Owners"，使高风险改动不能自合 PR。

### Trivy 版本为何必须 ≥ 0.35.0
审计清单 CICD-05：低于该版本存在供应链安全风险。
使用固定版本（`@0.35.0`）而非 `@latest`，避免 action 本身被恶意更新替换。

### 可以追问的问题
- workflow_dispatch 和 push 触发器有什么区别？
- GitHub Environment 保护规则怎么在 UI 里设置？
- Trivy 扫描的 CRITICAL/HIGH 是 CVE 级别吗？

---

## 审计修复：NET-02 / SEC-04 / BKP-02

### 做了什么

- **NET-02**：在 VPS 上配置 SSH 密钥登录（Ed25519），并禁用密码登录（`PasswordAuthentication no`）
- **SEC-04**：在 Miniflux 创建低权限用户 `scorer-worker`，生成专属 API Key，替换原来的 admin key；同时修复了 `deploy.sh` 中 shell 环境变量污染 docker compose 的问题
- **BKP-02**：在 `backup.sh` 末尾加入 7 天保留策略，自动清理过期备份目录

### 关键概念

**SSH 密钥认证 vs 密码认证**
密码登录每天面对全球几千次暴力破解尝试。密钥认证使用非对称加密：私钥只在你本机，服务器只存公钥。没有私钥，公钥毫无用处。禁用密码登录后，暴力破解攻击面归零。

**passphrase 和服务器密码是两回事**
`Enter passphrase for key '...'` 是在解锁本机私钥文件（本地操作，服务器看不到）。`root@x.x.x.x's password:` 才是服务器账号密码（网络传输，可被截获）。两者都出现"输密码"但含义完全不同。

**最小权限原则（Principle of Least Privilege）**
Scorer Worker 只需要读取文章，不需要增删订阅源或管理用户。给它 admin key 意味着：如果 Worker 容器被攻破，攻击者获得完整的 Miniflux 控制权。换成只读账号的 key，攻破 Worker 顶多泄露文章列表。

**shell 环境变量优先级高于 `--env-file`**
Docker Compose 解析变量的优先级：`shell env` > `--env-file` > compose 文件默认值。
如果 shell 里已有 `MINIFLUX_API_KEY=change_me`（被 pi agent 从 `.env.example` 注入），`--env-file .env` 里的正确值就会被忽略。解决方案：在 `deploy.sh` 开头 `unset` 所有敏感变量，让 `--env-file` 生效。

**`find -mtime +7` 清理逻辑**
`-mtime +7` 匹配"修改时间超过 7 天"的目录。`-maxdepth 1 -mindepth 1` 限定只看 `backup/` 的直接子目录，防止误删深层文件。`-print` 在删除前先打印路径，方便日志审计。

### 可以在学习 session 里追问的问题

- `ssh-keygen -t ed25519` 和 `-t rsa` 有什么区别？为什么 Ed25519 更推荐？
- Docker Compose 变量替换的完整优先级顺序是什么？
- `find` 命令的 `-mtime` / `-ctime` / `-atime` 分别是什么时间？
- Miniflux API Key 存在数据库哪张表里？

---

## Miniflux 首个订阅源抓取验证

### 做了什么

在生产环境的 Miniflux 页面里添加了第一个测试 RSS 源，并确认能抓取到文章。这个结果说明 Miniflux 服务、PostgreSQL 持久化、容器出站网络、Caddy/Authelia 入口认证都已经能配合工作。
随后在 Worker 容器内分别请求 `/v1/me` 和 `/v1/entries`，确认 API Key 有效、Docker 内网可达、Miniflux 已返回 unread entry。最后重建 scorer-worker，让它立即跑一轮，确认没有再出现 401。

### 关键概念

**RSS 阅读器不是搜索引擎**
Miniflux 不会自动抓取全网内容。它只会抓取你主动添加的 RSS/Atom 订阅源，所以“系统开始工作”的第一步是添加 feed，而不是修改 Worker。

**手动刷新 vs 后台轮询**
手动刷新适合验证单个订阅源是否可用；后台轮询由 Miniflux 的调度器定期执行，默认约每 60 分钟检查一批订阅源。生产环境里不需要一直手动刷新，但首次接入时手动刷新能快速判断网络和 feed URL 是否正常。

**Unread entries 是 Worker 的输入**
当前 Scorer Worker 查询的是 Miniflux API 里的 unread entries。只有 Miniflux 抓到了未读文章，Worker 才可能从之前的 `Fetched 0 entries` 变成抓到真实条目。

**用最小接口分层定位问题**
遇到 `/v1/entries` 返回 401 时，不应直接重启服务。先测 `/v1/me`：如果 `/v1/me` 也 401，说明 key 本身无效；如果 `/v1/me` 是 200，再测 `/v1/entries`，就能区分“认证问题”和“具体查询问题”。

**Worker 启动即执行一轮**
当前 scorer-worker 启动时会先执行一次抓取，然后再按 `SCORER_INTERVAL_SECONDS` 间隔循环。重建容器是一种手动触发立即验证的方式，不需要等下一小时。

### 可以在学习 session 里追问的问题

- RSS、Atom、网页 URL 三者有什么区别？为什么网页首页不一定能直接订阅？
- Miniflux 的后台轮询频率在哪里配置？
- 为什么 Worker 只读 unread entries，而不是全部历史文章？
- 为什么用 `/v1/me` 可以判断 API Key 是否有效？
- Docker 容器里访问 `http://miniflux:8080` 和 VPS 上访问 `localhost:8080` 有什么区别？

---

## Task 8 + 9: Runbooks 与生产前演练清单

### 做了什么
创建了 4 个运维手册（`docs/runbooks/`）：
- `deploy.md`：部署流程 + API Key 轮换步骤
- `rollback.md`：何时回滚、如何识别 last-known-good、验证命令
- `backup-restore.md`：备份命令、restore 流程、验证方式、pg_dump 格式说明
- `incident.md`：P1/P2/P3 分级、诊断 playbook、常见故障处理、上报流程

在审计清单中补了 runbook 互相引用（BKP-01/03, CICD-03）和 Task 9 生产前演练清单。

### 为什么 Runbook 比文档里的步骤更重要
没有 runbook 时，事故恢复会卡在：
1. 不知道该先看哪个服务的日志
2. 忘记回滚命令的参数顺序
3. 不知道回滚后如何验证是否成功
有了 runbook，凌晨 3 点出现故障，照着执行就能恢复，不需要依赖记忆。

### 演练过的回滚 vs 只写在文档里的回滚
"演练过"意味着你知道：
- 命令在当前服务器路径下能执行
- rollback.sh 参数顺序是对的
- 回滚后健康检查 URL 是可达的
仅写在文档里的回滚，第一次真正执行时往往会发现路径错误、权限问题、或者健康检查失败。

---

## Minimax LLM 评分与 Digest 入库

### 做了什么

新增了 Minimax LLM client，并把 `score_entry()` 从纯长度评分升级为“优先调用 LLM、失败时 fallback 到 baseline”的结构。当前阶段已经验证：模型返回严格 JSON 时会写入 Minimax 评分字段；模型超时、401 或返回非 JSON 时，Worker 不会整轮崩掉。

### 关键概念

**LLM API client 是什么**
API client 是项目里专门负责“怎么调用外部服务”的小模块。业务代码只关心“给我一个评分结果”，而不需要到处重复写 URL、Header、timeout、HTTP 错误处理。

**为什么要结构化 JSON 输出**
自然语言回答适合人读，但数据库和程序需要稳定字段。要求模型只返回 `score`、`tags`、`reason`、`confidence` 这类 JSON 字段，后续才能校验分数范围、限制 tag 数量，并安全写入 `item_scores`。

**fallback 为什么重要**
LLM 是外部依赖，可能因为网络、额度、API key、模型输出格式等原因失败。fallback 让 Worker 至少能保存 baseline 分数和错误状态，不会因为一篇文章失败就中断整轮抓取。

**为什么 digest 先入库**
第一版先把 digest 写进 scoring 数据库，而不是直接做邮件或 Web UI，是为了先固定“哪些文章值得读”的结果。后续无论要做网页、邮件、Telegram 推送，都是从同一张表读取，不需要重新跑 LLM 或重新扫日志。

**为什么要唯一约束和 `ON CONFLICT`**
Worker 重启、网络抖动或部署重试都可能让同一轮 digest 再跑一次。唯一约束定义“什么算同一份 digest”，`ON CONFLICT` 定义重复时怎么更新，避免数据库里出现多份内容相同的脏数据。

**API key 为什么不能进 Git**
Minimax API key 相当于外部服务的密码，泄露后别人可以用你的额度发请求。仓库里的 `.env.example` 只能写 `change_me` 这种占位值，真实 key 只放 VPS 的 `.env`，并且部署日志不能打印出来。

### 可以在学习 session 里追问的问题

- OpenAI-compatible API 是什么？为什么 Minimax 可以用 `/v1/chat/completions` 这种接口形状？
- `timeout` 和 HTTP 401 分别代表什么问题？
- 为什么模型输出 JSON 后还要在本地做二次校验？
- 数据库里的唯一约束和应用代码里的去重有什么区别？
- 如果 API key 不小心提交到了 Git，为什么“删掉再提交”还不够？

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
| 4 | 补充：首次部署前置（VPS / DNS / Secret） | 已记录 | 上机前动手清单，不等同于计划里的「Task 4」 |
| 5 | Task 6：运维脚本 | 已记录 | 与计划 **Task 6** 对齐 |

### 下一步可以学什么（新开 session 时从这里选）

1. **若优先「真机跑通」**：按「补充：首次部署前置」在 VPS 上起 edge + 某一环境，用浏览器验证 `reader` / `auth` 与证书；再对照 `Caddyfile` 理解每条路由。
2. **若按 MVP 计划推进编码**：打开实现计划，进入 **Task 4（TDD 最小闭环）**——与「本笔记补充章」不是同一个编号，避免混谈。
3. **若优先自动化**：计划中的 **Task 7（CI/CD）** 与 **Task 8（Runbook）**。

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

# 学习笔记（my_rss 项目）

> 用法：在另一个 Cursor Chat 里 @docs/learning-notes.md，然后对任意概念追问。

---

## Task 1：仓库骨架与 Compose 分层

### 做了什么
- 创建了 `.gitignore`、`.env.example`
- 创建了四个 Compose 文件：`edge.yml`、`base.yml`、`prod.yml`、`staging.yml`

### 关键概念

**为什么 .env 不能进 Git**
Git 的历史是永久的。即使你后来删掉了 .env，`git log` 里那条提交永远存在，
任何人 clone 后都能用 `git show` 找到密码。`.gitignore` 是第一道防线。

**Compose 文件为什么要分层（base / prod / staging）**
prod 和 staging 结构相同，只有别名和少数变量不同。
base.yml 定义共同结构，prod/staging.yml 只覆盖差异，
这样修改公共配置只需改一个地方。

**为什么 Caddy 要单独一个 edge.yml**
一台 VPS 的 80/443 端口只有一组。
如果 prod 和 staging 各自带一个 Caddy，第二个启动时会报"端口占用"。
解决方案：Caddy 独立启动一次（project: myrss-edge），
prod/staging 后端通过 Docker 网络别名告诉 Caddy 自己在哪里。

**三层网络（edge → app → data）**
- app 网络：Caddy ↔ Authelia ↔ Miniflux ↔ Worker 互通
- data 网络：Miniflux ↔ Worker ↔ PostgreSQL 互通
- Caddy 不在 data 网络 → 网关永远访问不到数据库

**网络别名（aliases）**
Caddyfile 里写死了 `miniflux-prod` 和 `miniflux-staging` 这两个名字。
prod.yml 给 Miniflux 容器设置 `aliases: [miniflux-prod]`，
staging.yml 设置 `aliases: [miniflux-staging]`。
这样同一个 Caddy 就能区分两套后端。

### 可以在学习 session 里追问的问题
- Docker 网络是怎么工作的？容器之间怎么找到对方？
- `external: true` 是什么意思？
- `docker compose -p` 的 project name 有什么用？
- `restart: unless-stopped` 和 `always` 有什么区别？
- `.env.example` 里的连接串格式 `postgres://user:pass@host:port/db` 怎么读？

---

## Task 2：Caddy + Authelia 入口认证

### 做了什么
- 创建了 `infra/caddy/Caddyfile`：四条路由规则（prod/staging 各一对）
- 创建了 `infra/authelia/configuration.yml`：认证网关规则手册
- 创建了 `infra/authelia/users_database.yml`：本地用户模板（密码用 argon2id 哈希）
- 创建了 `infra/postgres/init/001-create-databases.sh`：PG 初始化脚本

### 关键概念

**forward_auth 是什么**
每次请求到达 reader.<domain> 时，Caddy 先把请求"转问"Authelia：
"这个用户登录了吗？" Authelia 说 OK（HTTP 200）→ 请求继续到 Miniflux；
Authelia 说未登录（401/302）→ 浏览器被重定向到登录页。
整个过程对用户透明，就像在进门前先刷卡。

**为什么 auth.<domain> 不需要 forward_auth**
auth.<domain> 就是登录页本身（Authelia），如果登录页也要先登录才能进，就死循环了。

**access_control default_policy: deny + rules**
只写 `default_policy: deny` 不写 rules，相当于门卫说"所有人都不能进"。
rules 是例外列表：reader.<domain> 的用户只要通过二因子认证就放行。

**argon2id 哈希**
密码存储不能用明文，哈希是单向函数（无法从哈希反推密码）。
argon2id 的特点是"故意很慢"——暴力穷举需要消耗大量内存和时间，
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

> 待补充

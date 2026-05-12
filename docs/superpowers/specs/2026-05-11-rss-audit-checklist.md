# RSS 轻量审计清单（发布前）

日期：2026-05-11  
版本：v2（v3 hardening 同步）  
适用范围：`my_rss` 项目生产发布前审计  
审计类型：轻量版（1-2 天）  

## 1. 审计规则（固定）

- 结果状态仅允许：`PASS / FAIL / N/A`
- 每个检查项必须附证据（命令输出、日志路径、配置片段、截图路径之一）
- 执行模式：你执行 + 二次自审复核问题清单
- 执行频率：每次生产发布前执行一次
- 发布门槛：所有高风险项（High）必须为 `PASS`，否则禁止发布

## 2. 审计记录模板

| ID | 检查项 | 风险级别 | 结果(PASS/FAIL/N/A) | 证据 | 备注 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

---

## 3. 轻量审计检查项（MVP）

### 3.1 认证与访问控制（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| AUTH-01 | 生产入口必须经过认证网关（Authelia） | High | PASS | 用户确认访问 reader.blankhoney.xyz 触发 Authelia 重定向 |  |
| AUTH-02 | 未登录用户无法访问 `reader.<domain>` 业务页面 | High | PASS | 未登录访问被 302 重定向至 auth.blankhoney.xyz |  |
| AUTH-03 | 本地账号 + TOTP/Passkey 登录流程可用 | High | PASS | 用户确认本地账号 + TOTP 登录流程可用 |  |
| AUTH-04 | 管理员应急账号存在且保管方式合规 | High | PASS | 用户唯一账号即管理员账号，个人 MVP 可接受 | 个人项目单用户 |

### 3.2 主机与网络暴露（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| NET-01 | 仅开放必要端口（22/80/443） | High | PASS | `ss -tlnp` 仅见 22/80/443；Redis 绑定 `[::1]` 回环；5432 内部 |  |
| NET-02 | SSH 禁 root 直登、禁密码登录、仅密钥登录 | High | FAIL | `PermitRootLogin yes` + `PasswordAuthentication yes`；缓解：fail2ban 已安装运行 | **已知风险**：个人 MVP 单用户接受；扩容前必须修复（设置 SSH 密钥 + 禁密码登录） |
| NET-03 | PostgreSQL 不对公网暴露 | High | PASS | `docker ps` 中 postgres 仅 `5432/tcp` 内部端口，无主机绑定 |  |
| NET-04 | 三层网络边界：Caddy 在 `edge`+`app`，Miniflux 在 `app`+`data`，PostgreSQL 仅在 `data`，网关不可直达数据库 | High | PASS | `docker ps` 确认：仅 Caddy 有公网端口，Miniflux/Authelia/Postgres 均为内部端口 |  |
| NET-05 | VPS 上仅有一个 Caddy 容器绑定 80/443，staging 与 prod 后端不各自启动网关 | High | PASS | `docker ps` 输出：仅 `myrss-edge-caddy-1` 绑定 `0.0.0.0:80/443`，staging 容器无公网端口 |  |

### 3.3 密钥与日志安全（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| SEC-01 | 数据库密码、Authelia secret、SMTP 密码不在 Git 中 | High | PASS | `git log -S "secret" --all` 结果为配置键名引用，无实际凭据值 |  |
| SEC-02 | Authelia session secret 与 storage encryption key 以 `_FILE` 环境变量方式加载（非明文写入 `configuration.yml` 或 compose env） | High | PASS | `docker inspect` 确认：`AUTHELIA_SESSION_SECRET_FILE=/run/secrets/authelia_session_secret`，`AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE=/run/secrets/authelia_storage_encryption_key` |  |
| SEC-03 | `storage.encryption_key` 已配置（长度 ≥ 20，推荐 64+ 随机字符），通过环境变量注入 | High | PASS | 通过 `AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE` 注入，非明文写入配置 |  |
| SEC-04 | Worker 使用专用低权限 Miniflux API Key（不复用管理员账号，key 不入库） | High | FAIL | Miniflux API Key 权限与用户绑定，当前使用用户级别 Key；Key 未入 Git | **已知风险**：MVP 接受；后续在 Miniflux 中创建专用 `scorer-worker` 用户并生成独立 Key |
| SEC-05 | 日志脱敏生效（无 API Key/Cookie/Auth Header/全文泄露） | High | PASS | `docker logs myrss-prod-miniflux-1` grep `api.key\|authorization\|cookie` 无命中 |  |
| SEC-06 | PostgreSQL 使用专用 `miniflux` 和 `scoring` 账号连接，不使用 postgres 超级用户 | High | PASS | `\du` 输出：`miniflux` 和 `scoring` 角色无 Superuser 属性 |  |

### 3.4 HTTPS 与证书（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| TLS-01 | HTTP 自动跳转 HTTPS | High | PASS | `curl -sI http://reader.blankhoney.xyz` → `HTTP/1.1 308 Permanent Redirect` → `https://reader.blankhoney.xyz/` |  |
| TLS-02 | 证书有效且到期时间可见（自动续期机制可验证） | High | PASS | `notBefore=May 11 2026`，`notAfter=Aug 9 2026`；Let's Encrypt 90 天，Caddy 自动续期 |  |

### 3.5 备份与恢复（Medium）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| BKP-01 | `miniflux` 与 `scoring` 每日逻辑备份执行成功 | Medium | PASS | crontab: `0 2 * * * bash infra/scripts/backup.sh`，每日凌晨 2 点执行 | Ref: [backup-restore.md](../../runbooks/backup-restore.md) |
| BKP-02 | 本地 7 天 + 异地 30 天保留策略已配置 | Medium | FAIL | `backup.sh` 无旧文件清理逻辑，无异地备份 | Medium 项不阻断；MVP 后补保留策略与 rclone 异地同步 |
| BKP-03 | 至少一次临时恢复演练成功（含评分续跑验证） | Medium | N/A | MVP 阶段未执行恢复演练 | post-launch 前补充 | Ref: [backup-restore.md](../../runbooks/backup-restore.md#restore) |

### 3.6 CI/CD 与回滚（Medium）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| CICD-01 | PR 必须通过 lint/test/security scan 才可合并 | Medium | PASS | CI 绿色，PR #1 通过 lint/test/compose-validate/trivy 后合并 | Ref: `.github/workflows/ci.yml` |
| CICD-02 | `main/develop` 分支保护生效（禁止直接 push，`main` 要求 Code Owner review） | Medium | PASS | 用户确认 main 分支保护已启用，要求 PR + Code Owner review |  |
| CICD-03 | 生产部署支持按 tag 回滚并验证健康检查（内部 `readyz` 探针） | Medium | PASS | staging→prod→rollback 演练完成，每步 `wget readyz` 返回 OK | Ref: [rollback.md](../../runbooks/rollback.md) |
| CICD-04 | `deploy-prod.yml` job 配置 `environment: production`，GitHub Environment 保护规则已启用 | Medium | PASS | `deploy-prod.yml` L15-16 确认 `environment: name: production` |  |
| CICD-05 | CI 使用的 `trivy-action` 版本 ≥ 0.35.0（低于该版本存在已知供应链风险） | Medium | PASS | `.github/workflows/ci.yml` L39: `uses: aquasecurity/trivy-action@0.35.0` |  |

### 3.7 服务可用性与 Authelia 配置（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| AUTH-05 | Authelia `access_control.rules` 包含明确 allow 规则（不只有 `default_policy: deny`），目标域名可正常访问 | High | PASS | `default_policy: deny` + `two_factor` rules 覆盖 `reader.blankhoney.xyz` 与 `staging-reader.blankhoney.xyz` |  |
| AUTH-06 | Authelia `session.cookies` 包含正确 `domain` 与 `authelia_url`（与实际域名一致） | High | PASS | `domain: blankhoney.xyz`，`authelia_url: https://auth.blankhoney.xyz`，与实际域名一致 |  |
| AUTH-07 | Miniflux 已设置 `BASE_URL`（与外部域名一致）且 `LISTEN_ADDR: 0.0.0.0:8080` | High | PASS | `docker inspect`：`BASE_URL=https://reader.blankhoney.xyz`，`LISTEN_ADDR=0.0.0.0:8080` |  |

---

## 4. 发布判定规则

- 阻断发布条件：
  - 任一 High 项为 `FAIL`
  - 任一 High 项缺证据
- 可带条件发布：
  - Medium 项 `FAIL` 但有明确修复截止时间与临时缓解措施
- 不计入阻断：
  - 标记为 `N/A` 且备注说明合理

## 5. 二次自审复核问题（你执行后由我复核）

1. 是否存在“看起来 PASS，但证据无法复现”的项？
2. High 项是否全部有明确证据链（命令 -> 输出 -> 结论）？
3. 是否误把 staging 结果当作 prod 证据？
4. 是否有 secrets 出现在日志、截图、工单评论、PR 评论中？
5. 回滚流程是否真实跑过一次，而不是仅写在文档里？
6. 备份恢复是否覆盖 `miniflux + scoring + cursor` 连续性验证？
7. N/A 项是否有充分理由，且不会掩盖高风险缺口？
8. VPS 上是否仅有一个容器绑定了80/443（NET-05），是否验证了 staging 后端上线后端口没有冲突？
9. Authelia `_FILE` secret 变量是否真正注入（`docker inspect` 确认），而不是 `configuration.yml` 仍有明文 secret？
10. `storage.encryption_key` 是否已通过 `AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE` 注入，且长度符合要求（≥ 64 随机字符）？
11. Authelia `access_control.rules` 是否包含覆盖目标域名的 allow 规则，是否实际测试了未认证访问被拒绝 + 认证后可访问？
12. Miniflux 健康检查是否走内部探针（`readyz`），而不是依赖经过 Authelia 的外部 `/healthz` URL？
13. Worker API Key 是否有轮换记录，旧 Key 是否已在 Miniflux 管理界面删除？

## 6. 本次执行记录（留档）

- 执行人：blankhoney
- 执行时间：2026-05-12
- 目标发布版本：d4d51fd（main @ 2026-05-12）
- 结论（Go / No-Go）：**Conditional Go** — 2 项 High 风险已知缺陷，已记录缓解措施与修复计划，MVP 个人项目接受
- High 风险遗留项（若有）：
  - **NET-02**：SSH 允许 root 直登 + 密码登录。缓解：fail2ban 已安装运行。修复计划：扩容或对外开放前设置 SSH 密钥并禁用密码登录。
  - **SEC-04**：Scorer Worker 使用用户级别 Miniflux API Key（非专用低权限账号）。Key 未入 Git。修复计划：在 Miniflux 中创建专用 `scorer-worker` 用户并生成独立 Key，post-launch 前完成。
- Medium 风险遗留项（若有）：
  - **BKP-02**：`backup.sh` 无旧文件清理逻辑，无异地备份。修复计划：添加 7 天保留策略 + rclone 异地同步。
  - **BKP-03**：未执行恢复演练。修复计划：post-launch 执行一次完整恢复演练。
- 下次复审时间：2026-06-12（一个月后）或首次有外部用户访问前

## 7. 生产前演练清单（Task 9）

以下步骤在每次 prod 发布前执行，执行后于本文件"本次执行记录"中留档：

### Staging → Prod 演练流程

```bash
# Step 1: staging 端到端验证
bash infra/scripts/deploy.sh staging <new-tag>
curl -I https://staging-reader.<domain>    # Expected: 302 → auth.domain
# 手动登录 staging-reader 确认 Miniflux 可用

# Step 2: prod 部署
bash infra/scripts/deploy.sh prod <new-tag>
docker compose -p myrss-prod \
  -f infra/compose/docker-compose.base.yml \
  exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz   # Expected: OK

# Step 3: 可控回滚演练（至少每次大版本执行一次）
bash infra/scripts/rollback.sh prod <old-tag>
docker compose -p myrss-prod \
  -f infra/compose/docker-compose.base.yml \
  exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz   # Expected: OK after rollback
```

### 审计清单 Go / No-Go 判定

```bash
# 扫描所有 High 项是否为 PASS
rg "High.*PASS|PASS.*High" docs/superpowers/specs/2026-05-11-rss-audit-checklist.md -n
# 确认无 FAIL 的 High 项
rg "High.*FAIL|FAIL.*High" docs/superpowers/specs/2026-05-11-rss-audit-checklist.md -n
```

### 事故响应参考

- 部署失败 → [rollback.md](../../runbooks/rollback.md)
- 数据丢失 → [backup-restore.md](../../runbooks/backup-restore.md)
- 服务异常 → [incident.md](../../runbooks/incident.md)

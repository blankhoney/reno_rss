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
| AUTH-01 | 生产入口必须经过认证网关（Authelia） | High |  |  |  |
| AUTH-02 | 未登录用户无法访问 `reader.<domain>` 业务页面 | High |  |  |  |
| AUTH-03 | 本地账号 + TOTP/Passkey 登录流程可用 | High |  |  |  |
| AUTH-04 | 管理员应急账号存在且保管方式合规 | High |  |  |  |

### 3.2 主机与网络暴露（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| NET-01 | 仅开放必要端口（22/80/443） | High |  |  |  |
| NET-02 | SSH 禁 root 直登、禁密码登录、仅密钥登录 | High |  |  |  |
| NET-03 | PostgreSQL 不对公网暴露 | High |  |  |  |
| NET-04 | 三层网络边界：Caddy 在 `edge`+`app`，Miniflux 在 `app`+`data`，PostgreSQL 仅在 `data`，网关不可直达数据库 | High |  |  | `docker network inspect` 或 compose config 截图 |
| NET-05 | VPS 上仅有一个 Caddy 容器绑定 80/443，staging 与 prod 后端不各自启动网关 | High |  |  | `docker ps --format "{{.Names}} {{.Ports}}"` 输出 |

### 3.3 密钥与日志安全（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| SEC-01 | 数据库密码、Authelia secret、SMTP 密码不在 Git 中 | High |  |  | `git log -S "secret" --all` 无命中 |
| SEC-02 | Authelia session secret 与 storage encryption key 以 `_FILE` 环境变量方式加载（非明文写入 `configuration.yml` 或 compose env） | High |  |  | `docker inspect` 确认 `AUTHELIA_SESSION_SECRET_FILE` 等变量存在 |
| SEC-03 | `storage.encryption_key` 已配置（长度 ≥ 20，推荐 64+ 随机字符），通过环境变量注入 | High |  |  |  |
| SEC-04 | Worker 使用专用低权限 Miniflux API Key（不复用管理员账号，key 不入库） | High |  |  |  |
| SEC-05 | 日志脱敏生效（无 API Key/Cookie/Auth Header/全文泄露） | High |  |  |  |
| SEC-06 | PostgreSQL 使用专用 `miniflux` 和 `scoring` 账号连接，不使用 postgres 超级用户 | High |  |  | `psql -U postgres -c "\du"` 输出 |

### 3.4 HTTPS 与证书（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| TLS-01 | HTTP 自动跳转 HTTPS | High |  |  |  |
| TLS-02 | 证书有效且到期时间可见（自动续期机制可验证） | High |  |  |  |

### 3.5 备份与恢复（Medium）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| BKP-01 | `miniflux` 与 `scoring` 每日逻辑备份执行成功 | Medium |  |  |  |
| BKP-02 | 本地 7 天 + 异地 30 天保留策略已配置 | Medium |  |  |  |
| BKP-03 | 至少一次临时恢复演练成功（含评分续跑验证） | Medium |  |  |  |

### 3.6 CI/CD 与回滚（Medium）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| CICD-01 | PR 必须通过 lint/test/security scan 才可合并 | Medium |  |  |  |
| CICD-02 | `main/develop` 分支保护生效（禁止直接 push，`main` 要求 Code Owner review） | Medium |  |  | GitHub repo settings 截图 |
| CICD-03 | 生产部署支持按 tag 回滚并验证健康检查（内部 `readyz` 探针） | Medium |  |  |  |
| CICD-04 | `deploy-prod.yml` job 配置 `environment: production`，GitHub Environment 保护规则已启用 | Medium |  |  | GitHub Environments 配置截图 |
| CICD-05 | CI 使用的 `trivy-action` 版本 ≥ 0.35.0（低于该版本存在已知供应链风险） | Medium |  |  | `.github/workflows/ci.yml` 片段 |

### 3.7 服务可用性与 Authelia 配置（High）

| ID | 检查项 | 风险级别 | 结果 | 证据 | 备注 |
|---|---|---|---|---|---|
| AUTH-05 | Authelia `access_control.rules` 包含明确 allow 规则（不只有 `default_policy: deny`），目标域名可正常访问 | High |  |  | `rg "rules:" infra/authelia/configuration.yml` |
| AUTH-06 | Authelia `session.cookies` 包含正确 `domain` 与 `authelia_url`（与实际域名一致） | High |  |  |  |
| AUTH-07 | Miniflux 已设置 `BASE_URL`（与外部域名一致）且 `LISTEN_ADDR: 0.0.0.0:8080` | High |  |  | `docker inspect` 环境变量 |

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

- 执行人：
- 执行时间：
- 目标发布版本：
- 结论（Go / No-Go）：
- High 风险遗留项（若有）：
- Medium 风险遗留项（若有）：
- 下次复审时间：

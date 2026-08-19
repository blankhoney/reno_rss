# CI/CD 规格

[English](SPEC-CICD.md) | [中文](SPEC-CICD.zh-CN.md)

## 背景

Reno RSS / AI Reader 已具备 GitHub Actions 检查、GHCR 镜像发布、可信 VPS 发布事务和 smoke test。Pull request 执行 checks；push 到 `refs/heads/main` 执行 checks，并发布绑定完整 SHA 的 digest 镜像及 publication evidence。`ci.yml` 的镜像 job 不修改 VPS。手动 request workflow 只创建不可变 request artifact；`trusted-deploy.yml` 只有在验证 provenance 以及对应 SHA 的 canonical main CI publication 后才消费该 artifact。

本规格记录这套现行交付契约，以及维持它所需的证据。

## 目标

- staging 或 production 只能通过已验证的 trusted release workflow 部署；pull request 和 canonical 镜像构建都不修改 VPS。
- request 输入保持手动创建，然后由 `trusted-deploy.yml` 应用 `staging` 或 `production` GitHub Environment 并执行携带 secret 的事务。production 必须通过该 environment 审批。
- 应用镜像在 GitHub Actions 中构建，VPS 只从 GHCR 拉取镜像运行。
- runtime secret 保存在 VPS 或 GitHub Secrets，不在日志中打印。
- 失败原因可归类为检查失败、镜像构建失败、SSH/secret 失败、VPS 工作树脏、部署失败或 smoke test 失败。

## 非目标

- 不引入 Kubernetes、自托管 runner 或新的部署平台。
- 不从 `main` 自动部署 production。
- 不在 CI 中重写 Git 历史或迁移服务器 secret。
- 不在自动 smoke test 中调用 MiniMax 评分或 Agent 问答，避免产生不必要成本。

## 用户故事

- 作为维护者，我为已成功发布的 SHA 创建有效 staging request 后，trusted workflow 应在 provenance 和 environment gate 通过后执行。
- 作为维护者，我不应直接 SSH 部署；trusted workflow 负责唯一的加锁 SSH 事务。
- 作为访客，staging app 应持续提供共享用户的功能 demo，同时保持管理员操作的 role 保护。
- 作为维护者，production 只有在 trusted orchestrator 执行并完成手动审批后才应改变。

## 功能需求

- `ci.yml` 必须执行 Python test/lint、reader-web test/build、Compose 校验，以及显式 Trivy high/critical 漏洞与 secret 扫描。
- `ci.yml` 必须将 `ai-reader-web`、`ai-reader-api` 和 `ai-reader-worker` 镜像发布到 GHCR，并使用 canonical `sha-<完整 40 位 SHA>` tag（short tag 只作为兼容别名）。
- Pull request 事件只执行 checks。push 到 `refs/heads/main` 发布镜像和不可变 publication evidence，但不部署 staging。手动 staging request 只有在 `trusted-deploy.yml` 验证 request 及 matching canonical publication 后才执行。
- 外部 fork PR 不部署，也不能读取部署 secret。
- `deploy-staging.yml`、`deploy-prod.yml` 和 `rollback.yml` 是按明确 immutable `sha-<完整 SHA>` tag 与完整 deploy SHA 创建手动 request 的入口，只写入固定 request artifact。
- production request 另外要求三个互不相同的 trusted run ID（staging deploy、rollback drill、forward deploy）、不同于 candidate 的 rollback-target SHA、固定的 current-main control-plane SHA，以及精确的 release-record ref 与 SHA-256 digest；单独的 `trusted-production-promotion-proof` artifact 只是数据，verifier 必须读取并验证真实成功 receipt artifact 与 release record 的 provenance/content/digest，并绑定 candidate 与 control-plane SHA。
- `trusted-deploy.yml` 必须先验证 completed request run、workflow identity/path、repository/ref/SHA、exact artifact、operation 的成功 canonical `ci.yml` image publication，以及 current-main control-plane SHA 唯一成功的 canonical CI run，之后 execute job 才能运行。
- execute job 使用 `staging` 或 `production` GitHub Environment；production 没有 `production` environment 审批及其 scoped secrets 就不能执行。
- 三个手工 workflow 都不得 checkout 仓库代码、读取部署 secret、申请 `packages: write` 或执行 SSH/远程部署脚本；它们的 artifact 只是数据，不是可执行命令。
- trusted remote transaction 必须检查 VPS tracked 工作树；预置 helper checksum 不匹配、工作树不干净、operation SHA 不是已抓取 trusted `main` control-plane SHA 的 ancestor 时必须停止。
- staging smoke test 必须通过不改业务数据的检查验证容器、health endpoint、公开 AI Reader 工作台、匿名文章 `200` 和匿名 Admin `403`；不得调用会标记已读、补全文、同步、评分、调用 Agent 或写业务数据的动作。

## 非功能需求

- **安全**：不得打印 secret、cookie、SSH key、API key 或 Basic Auth header。
- **可追踪**：request artifact 必须包含完整 deploy SHA 和 immutable image tag；trusted orchestrator 执行后记录镜像、目标 URL 和 smoke test 成功结果。
- **幂等**：trusted path 重复部署同一 image tag 应收敛到同一服务状态，不需要手动清理。
- **环境隔离**：staging 自动化不得部署 production。
- **成本控制**：自动 smoke test 不触发 LLM 评分或 Agent 调用。

## 接口与边界

- **GitHub Actions**：`ci.yml` 负责 checks 和镜像 publication。`deploy-staging.yml`、`deploy-prod.yml`、`rollback.yml` 是手动 request 路径；artifact 是数据而不是命令，这些 job 不读取部署 secret。`trusted-deploy.yml` 是 trusted execution 路径：verify job 校验 completed request run、allowlisted workflow identity/path、repository/ref/SHA、exact artifact、operation 的 canonical `ci.yml` publication，以及 current-main control plane 的成功 canonical CI。只有 verify 成功才进入 execute；execute checkout 该精确 control-plane SHA，声明 `staging` 或 `production` Environment，读取 scoped SSH/GHCR secret，按 `VPS_PORT` 验证 exact known-hosts entry，并执行远程事务。provenance gate 必须位于全部部署 secret 读取和 mutation 之前。
- **Request 输入**：`deploy-staging.yml` 接受 `image_tag` 与完整 `deploy_sha`；`rollback.yml` 另外接受 `env`，值只能是 `staging` 或 `prod`。`deploy-prod.yml` 还强制要求 staging/rollback/forward 三个 run ID、不同的 rollback target、current-main control-plane SHA，以及固定 release-record ref/digest。三个入口都拒绝 `git_ref`。
- **Request artifact**：每个手动请求上传一个固定 JSON artifact，且只含 `schema_version`、`request_type`、`environment`、`image_tag` 和 `deploy_sha`。`schema_version` 固定为 `trusted-deploy-request/v1`；`image_tag` 必须是 `sha-<40 位小写十六进制>`，并等于完整 40 位小写 `deploy_sha`。artifact 只是数据，不能执行其内容。
- **Production promotion proof**：`deploy-prod.yml` 另外上传 `trusted-production-promotion-proof`（`trusted-production-promotion/v1`），把 candidate 绑定到三个不同的 staging run：部署 candidate、从 candidate 回滚到不同 target、再从该 target 前滚到 candidate。receipt artifact 名称包含 environment、request type、run 和 operation SHA。release record 必须精确为 `<control-plane SHA>:docs/releases/<candidate SHA>.json`；其严格 `rss-production-release/v1` 内容绑定 candidate CI run/attempt、publication artifact ID 与 GitHub digest、三个 image digest、三段 run ID、rollback target，以及 backup/migration/rollback plan。`trusted-deploy.yml` 会验证真实 run、严格 receipt archive、状态转换、release-record bytes 与 digest；输入字段或人工声称的 success 本身不是证据。
- **固定 artifact 名称**：staging 为 `trusted-staging-deploy-request`，production 为 `trusted-production-deploy-request`，rollback 为 `trusted-rollback-request`。
- **部署 secret 与 SSH**：execute 需要配置的 `VPS_SSH_KEY` 或 `VPS_SSH_KEY_B64`、`VPS_HOST`、`VPS_PORT`、`VPS_USER`、`VPS_APP_DIR`、`VPS_KNOWN_HOSTS`、`GHCR_USERNAME`、`GHCR_TOKEN`，以及包含预置 shared-lock wrapper/core/transaction SHA-256 的 repository variables。值不会打印。`VPS_KNOWN_HOSTS` 必须匹配实际 host/port；禁止使用 `ssh-keyscan`。
- **Canonical shared lock**：在首次远程文件 mutation 前，SSH command 只做 helper 预检并只调用一次 public wrapper。wrapper 在整个事务期间持有 `/var/lib/reno-shared-vps/release-lock-v1/release.lock`，覆盖 bundle 接收、backup、Caddy/edge 恢复、migration、activation、probe 和 compensation。metadata 在 `/var/lib/reno-shared-vps/release-lock-v1/metadata.json`，audit/quarantine 在 `/var/lib/reno-shared-vps/release-lock-v1/audit/`。workflow concurrency 只解决同仓排队，不能替代 VPS lock。
- **Bootstrap 前置**：必须先由单独授权、root 运行的 `infra/deploy/bootstrap-shared-release-v1.sh` 预置 canonical lock tree，并在 `/usr/local/lib/reno-shared-vps/release-lock-v1/` 安装 checksum 固定、root-owned helper。owner、权限、symlink、group 或 checksum 不安全时 fail closed。production、staging、rollback、compensation 都不会调用 bootstrap。
- **Trusted remote deploy**：`.github/scripts/remote-deploy.sh` 在锁内校验 manifest 及候选 bundle 内嵌的 probe/edge/rollback contract，登录 GHCR，抓取 `refs/heads/main`，要求 control-plane SHA 等于抓取的 main tip，且 operation SHA 是其 ancestor；之后验证 digest-qualified image 与 OCI revision，再执行 deploy、migration、backup、smoke、edge 恢复和 runtime 检查。
- **Production backup gate**：`infra/scripts/deploy.sh` 在其 Compose pull/up、migration 或 edge activation 前验证 fresh production database backup；备份或 checksum 失败时停止事务，并保持当前 runtime 不变。
- **Receipt 与 probe**：每个事务记录 `pre-mutation`、`pre-activation`，以及 `post-activation`、`post-rollback` 或 `post-compensation` 之一的 cross-site receipt。每份 receipt 绑定 contract version、`owner`、operation SHA、workflow run、phase、实际 runtime SHA、UTC timestamp、固定 RSS/Blog URL 结果及 Caddy/edge 状态。probe 使用有界 HTTPS GET 与固定 allowlist：RSS 必须通过 auth redirect 后最终 HTTPS 可达，Blog 必须 TLS 公开返回 `200`；Docker JSON inspect 必须证明 Caddy 同时属于 `myrss-app` 与 `brianstorm-edge`、driver/config/upstream 正常、production Blog 成员正确，且 staging web 不在 production edge。未知 phase/key、非法 URL 或任一站点/edge 失败都不得写成功 receipt，并阻止晋级。
- **Rollback provenance 边界**：rollback request 的 operation SHA 是目标 runtime，且必须具备 canonical main publication evidence。事务把实际 pre-activation runtime 记录为 `rollbackFrom`；`post-rollback` 的 runtime 等于 target，`post-compensation` 的 runtime 回到 `rollbackFrom`。compensation 读取实际 current：current 已是 `rollbackFrom` 时只 probe；current 是失败 target 时才按 expected target 激活 `rollbackFrom`；未知状态 fail closed。
- **Smoke test**：`infra/scripts/smoke-test.sh` 验证运行时健康，不打印 secret，也不修改业务数据。
- **VPS runtime state**：`.env`、Authelia 用户库和其他 runtime secret 保留在 Git 外。

## 验收标准

- `main` push 触发成功的 canonical `ci` image publication，三个镜像和 evidence 都绑定完整 SHA。
- 有效 staging request 使 `trusted-deploy.yml` 通过 provenance、声明 `staging` Environment、在首次 mutation 前取得 canonical VPS lock，并完成远程部署与 cross-site receipt。
- 有效 production request 只能在相同事务通过 `production` Environment 审批后执行；main push 本身不改变 production。
- staging public endpoint 与配置的 reader route 展示功能 demo；trusted receipt 同时证明 RSS auth redirect/final reachability 和 Blog public route。
- 匿名 `GET /api/articles` 返回 `200`，匿名 Admin 请求返回 `403`。
- production 只有在 trusted workflow 消费手动创建的 `deploy-prod.yml` request、验证 current-SHA publication 及全部 gate，并通过 `production` Environment 审批后才改变。

## 运维阻塞处理

如果后续 trusted remote deploy 报告 VPS tracked 工作树脏，不要自动 reset。先诊断 dirty 文件：

- 临时服务器改动：人工确认后恢复仓库版本
- 必须保留的 runtime 设置：迁移到 `.env` 或 ignored runtime 文件
- 不确定改动：停止并报告 diff，且不要打印 secret

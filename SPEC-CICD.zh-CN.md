# CI/CD 规格

[English](SPEC-CICD.md) | [中文](SPEC-CICD.zh-CN.md)

## 背景

Reno RSS / AI Reader 已具备 GitHub Actions 检查、GHCR 镜像发布、VPS 远程部署脚本和 smoke test。当前 `ci.yml` 对 pull request 事件只执行 checks；只有 push 到 `refs/heads/main` 才执行测试、构建、发布、进入 staging deploy path 和 smoke。该 staging path 在 `VPS_KNOWN_HOSTS` 不可用时 fail closed，VPS 仓库存在 tracked 本地改动时远程路径也会停止。

本规格记录这套现行交付契约，以及维持它所需的证据。

## 目标

- 只有 push 到 `refs/heads/main` 通过检查后才部署 staging；pull request 事件只执行 checks。
- production 保持手动创建部署请求；后续 trusted orchestrator 负责 GitHub Environment 审批和携带 secret 的执行。
- 应用镜像在 GitHub Actions 中构建，VPS 只从 GHCR 拉取镜像运行。
- runtime secret 保存在 VPS 或 GitHub Secrets，不在日志中打印。
- 失败原因可归类为检查失败、镜像构建失败、SSH/secret 失败、VPS 工作树脏、部署失败或 smoke test 失败。

## 非目标

- 不引入 Kubernetes、自托管 runner 或新的部署平台。
- 不从 `main` 自动部署 production。
- 不在 CI 中重写 Git 历史或迁移服务器 secret。
- 不在自动 smoke test 中调用 MiniMax 评分或 Agent 问答，避免产生不必要成本。

## 用户故事

- 作为维护者，我 push 到 `main` 后，staging 应在检查通过后自动更新。
- 作为维护者，常规 staging 部署不应再 SSH 登录 VPS。
- 作为访客，staging app 应持续提供共享用户的功能 demo，同时保持管理员操作的 role 保护。
- 作为维护者，production 只有在 trusted orchestrator 执行并完成手动审批后才应改变。

## 功能需求

- `ci.yml` 必须执行 Python test/lint、reader-web test/build、Compose 校验，以及显式 Trivy high/critical 漏洞与 secret 扫描。
- `ci.yml` 必须将 `ai-reader-web`、`ai-reader-api` 和 `ai-reader-worker` 镜像发布到 GHCR，并使用 `sha-<short_sha>` tag。
- Pull request 事件只执行 checks；只有 push 到 `refs/heads/main` 才会在镜像发布后进入 staging deploy path；当 `VPS_KNOWN_HOSTS` 不可用时，该路径仍会 fail closed。
- 外部 fork PR 不部署，也不能读取部署 secret。
- `deploy-staging.yml` 是按明确 immutable image tag 和完整 deploy SHA 创建手动请求的入口，不直接部署。
- `deploy-prod.yml` 是创建手动 production 请求的入口；trusted orchestrator 启用后，必须由它应用 `production` environment 审批再部署。
- `rollback.yml` 是按明确 immutable image tag 和完整 deploy SHA 创建手动回滚请求的入口，不直接回滚。
- 三个手工 workflow 都不得 checkout 仓库代码、读取部署 secret、申请 `packages: write` 或执行 SSH/远程部署脚本。
- Remote deploy 必须在后续 trusted path 中检查 VPS tracked 工作树；工作树不干净时必须停止。
- staging smoke test 必须通过不改业务数据的检查验证容器、health endpoint、公开 AI Reader 工作台、匿名文章 `200` 和匿名 Admin `403`；不得调用会标记已读、补全文、同步、评分、调用 Agent 或写业务数据的动作。

## 非功能需求

- **安全**：不得打印 secret、cookie、SSH key、API key 或 Basic Auth header。
- **可追踪**：request artifact 必须包含完整 deploy SHA 和 immutable image tag；trusted orchestrator 执行后记录镜像、目标 URL 和 smoke test 成功结果。
- **幂等**：trusted path 重复部署同一 image tag 应收敛到同一服务状态，不需要手动清理。
- **环境隔离**：staging 自动化不得部署 production。
- **成本控制**：自动 smoke test 不触发 LLM 评分或 Agent 调用。

## 接口与边界

- **GitHub Actions**：`ci.yml` 是常规路径；`deploy-staging.yml`、`deploy-prod.yml` 和 `rollback.yml` 是手动 request-only 路径。GitHub 从用户选定的 dispatch ref 加载 workflow YAML，但 request job 不 checkout 或执行目标 repository code，也不访问部署 secret。当前新增的 `trusted-deploy.yml` 仅执行 verify-only：从 default main checkout 校验 completed request run、artifact、repository/ref/SHA 和 canonical `ci.yml` publication provenance，随后停止，不声明 environment、不读取 secret、不 SSH、不部署。其 workflow-ID allowlist 在 maintainer 提供控制面证据前保持未登记，因此 fail closed。后续执行阶段必须在读取部署 secret 前保留这道 provenance gate。
- **Request 输入**：`deploy-staging.yml` 和 `deploy-prod.yml` 只接受 `image_tag` 与完整 `deploy_sha`；`rollback.yml` 另外接受 `env`，值只能是 `staging` 或 `prod`。三个入口都拒绝 `git_ref`。
- **Request artifact**：每个手动请求上传一个固定 JSON artifact，且只含 `schema_version`、`request_type`、`environment`、`image_tag` 和 `deploy_sha`。`schema_version` 固定为 `trusted-deploy-request/v1`；`image_tag` 必须是 `sha-<7 位小写十六进制>`，并匹配完整 40 位小写 `deploy_sha` 的前七位。artifact 只是数据，不能执行其内容。
- **固定 artifact 名称**：staging 为 `trusted-staging-deploy-request`，production 为 `trusted-production-deploy-request`，rollback 为 `trusted-rollback-request`。
- **Rollback provenance 边界**：`trusted-deploy.yml` 现在校验 rollback request run、固定 artifact、canonical repository/main provenance，以及目标 SHA 对应的成功 canonical `ci.yml` publication；但它仍是 verify-only，不能选择 environment，也不能部署。remote contract 固定使用 `refs/heads/main`，只有目标 SHA 存在且是 fetched main tip 的 ancestor 时才继续（`.github/scripts/remote-deploy.sh:39-42,108-138`）。不得恢复任意 `git_ref` 输入，也不得把已废弃的 `FETCH_HEAD^{commit} == DEPLOY_SHA` equality 当作执行契约。
- **Trusted orchestrator 边界**：当前 trusted orchestrator 尚未启用，创建 request 不会自动部署或回滚。未来 trusted workflow 消费 artifact 数据，应用 environment 审批和 secret，并可复用已经验证的远程部署路径。
- **Remote deploy**：`.github/scripts/remote-deploy.sh` 是后续 trusted orchestrator 的执行路径。它 SSH 到 `VPS_APP_DIR`，确认 tracked 工作树干净，checkout `DEPLOY_SHA`，登录 GHCR，然后运行 `infra/scripts/deploy.sh`。
- **Smoke test**：`infra/scripts/smoke-test.sh` 验证运行时健康，不打印 secret，也不修改业务数据。
- **VPS runtime state**：`.env`、Authelia 用户库和其他 runtime secret 保留在 Git 外。

## 验收标准

- `main` push 触发的 `ci` workflow 中，`deploy staging` 运行而不是 skipped。
- workflow 发布三个带 `sha-<short_sha>` tag 的 GHCR 镜像。
- staging deploy job 成功完成远程部署和 smoke test。
- `https://staging-ai-reader.blankhoney.xyz/` 和 `/?module=all&sort=default&lang=zh` 展示公开的功能 demo。
- 匿名 `GET /api/articles` 返回 `200`，匿名 Admin 请求返回 `403`。
- production 只有在 trusted orchestrator 消费手动创建的 `deploy-prod.yml` request 并应用 `production` 审批后才改变。

## 运维阻塞处理

如果后续 trusted remote deploy 报告 VPS tracked 工作树脏，不要自动 reset。先诊断 dirty 文件：

- 临时服务器改动：人工确认后恢复仓库版本
- 必须保留的 runtime 设置：迁移到 `.env` 或 ignored runtime 文件
- 不确定改动：停止并报告 diff，且不要打印 secret

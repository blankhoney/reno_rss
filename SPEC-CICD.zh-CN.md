# CI/CD 规格

[English](SPEC-CICD.md) | [中文](SPEC-CICD.zh-CN.md)

## 背景

Reno RSS / AI Reader 已经具备 GitHub Actions 检查、GHCR 镜像发布、VPS 远程部署脚本和 smoke test。当前剩余交付缺口是：`main` push 成功后只构建镜像，不会自动部署 staging；手动 staging 部署还可能因为 VPS 仓库存在 tracked 本地改动而被阻塞。

本规格定义正常开发交付的目标行为：推送到 `main` 后，应自动完成测试、构建、发布镜像、部署 staging 和 smoke test，不再需要手动登录 VPS 操作。

## 目标

- 同仓库 PR 更新或 `main` push 通过检查后自动部署 staging。
- production 继续手动发布，并由 GitHub `production` environment 保护。
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
- 作为访客，简历 Demo URL 应持续展示公开 Landing，并允许游客进入体验。
- 作为维护者，production 必须经过 GitHub 手动审批后才改变。

## 功能需求

- `ci.yml` 必须执行 Python test/lint、reader-web test/build、Compose 校验和 Trivy high/critical 扫描。
- `ci.yml` 必须将 `ai-reader-web`、`ai-reader-api` 和 `ai-reader-worker` 镜像发布到 GHCR，并使用 `sha-<short_sha>` tag。
- 同仓库 PR 和 `main` push 必须在镜像发布后部署 staging。
- 外部 fork PR 不部署，也不能读取部署 secret。
- `deploy-staging.yml` 保留为按 image tag 手动部署的兜底入口。
- `deploy-prod.yml` 保持手动触发，并使用 `production` environment。
- `rollback.yml` 继续通过同一套远程部署路径回滚到旧镜像 tag。
- VPS tracked 工作树不干净时，远程部署必须停止。
- staging smoke test 必须通过只读 GET / 不改业务数据的检查验证容器、health endpoint、公开 Demo Landing 和业务路径保护边界；不得打开会标记已读、补全文、同步、评分、调用 Agent 或写业务数据的 reader 页面/API。

## 非功能需求

- **安全**：不得打印 secret、cookie、SSH key、API key 或 Basic Auth header。
- **可追踪**：workflow summary 必须包含 commit SHA、image tag、镜像、staging URL 和 smoke test 成功结果。
- **幂等**：重复部署同一 image tag 应收敛到同一服务状态，不需要手动清理。
- **环境隔离**：staging 自动化不得部署 production。
- **成本控制**：自动 smoke test 不触发 LLM 评分或 Agent 调用。

## 接口与边界

- **GitHub Actions**：`ci.yml` 是常规路径；`deploy-staging.yml`、`deploy-prod.yml`、`rollback.yml` 是手动控制路径。
- **镜像 tag**：部署 tag 为 `sha-<short_sha>`，必须与部署代码 revision 对齐。
- **远程部署**：`.github/scripts/remote-deploy.sh` SSH 到 `VPS_APP_DIR`，确认 tracked 工作树干净，checkout `DEPLOY_SHA`，登录 GHCR，然后运行 `infra/scripts/deploy.sh`。
- **Smoke test**：`infra/scripts/smoke-test.sh` 验证运行时健康，不打印 secret，也不修改业务数据。
- **VPS runtime state**：`.env`、Authelia 用户库和其他 runtime secret 保留在 Git 外。

## 验收标准

- `main` push 触发的 `ci` workflow 中，`deploy staging` 运行而不是 skipped。
- workflow 发布三个带 `sha-<short_sha>` tag 的 GHCR 镜像。
- staging deploy job 成功完成远程部署和 smoke test。
- `https://staging-ai-reader.blankhoney.xyz/` 展示公开 Demo Landing。
- 未登录请求 `https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh` 不直接暴露业务 UI。
- production 只有在手动运行并审批 `deploy-prod.yml` 后才改变。

## 运维阻塞处理

如果远程部署报告 VPS tracked 工作树脏，不要自动 reset。先诊断 dirty 文件：

- 临时服务器改动：人工确认后恢复仓库版本
- 必须保留的 runtime 设置：迁移到 `.env` 或 ignored runtime 文件
- 不确定改动：停止并报告 diff，且不要打印 secret

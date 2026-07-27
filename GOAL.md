# Project Optimization Goal

## 0. Document Contract

该文件是 `AI Reader` 这次长期迭代的权威合同，包含：单一目标、边界、优先级、验收、决策与停机条件。
`AGENTS.md` 规定了持续执行的工程规则；`PLANS.md` 记录执行日志与当前进度。两者冲突时优先级为：`AGENTS.md` ＞ `GOAL.md` ＞ `PLANS.md`。
`PLANS.md` 必须只记录“当前待做项”和可执行证据，`GOAL.md` 负责“终态与标准”。

本合同不允许：

1) 将未验证的数据写成真实基线；2) 因缺少外部服务/秘钥/浏览器/生产权限将任务定义为“阻塞”；3) 引入手工审批才可继续的计划；4) 把主观优化（例如“更漂亮”）当作完成标准；5) 删除、回滚或重写用户正在使用的核心业务契约。

执行规则：

- 所有未通过门控的缺口必须写成 `NEEDS_BASELINE` 或 `IN_PROGRESS`，而不是 PASS。
- 外部依赖缺失时采用替代顺序：**现有确定性事实契约 → 本地适配/Mock/回退方案 → 可重放本地服务 → CI 现场服务**，并继续独立推进其他项，不得把任务挂起等待人类确认。
- `docs/session-handoff.md` 与 `docs/learning-notes.md` 的更新用于交接与长期可操作性；任何一次成功执行后必须留下可复验路径与证据。

## 1. Primary Objective

为自托管研究者与小团队，优化 AI Reader 成为一套可无人值守持续进化的“研究主线保真系统”：

- 核心流程（Daily Intelligence / Scan / Focus / Keep / Ask / Search / Research / Review / Export）在上下文、状态、权限和失败恢复上可预测；
- 标注（高亮/笔记）在内容变化、重复文本、失效定位、会话切换场景下不发生“错误绑定”；
- 生产边界（页面路由、API 授权、Admin、secret）保持清晰且可验证；
- 所有关键体验变化可由自动化验证、可复用基线与可回滚发布证据支撑；
- 目标达成条件是：一个明确 SHA 的当前仓库修订版通过全部 MUST 验收、通过完整里程碑，并在自动化记录中可无外部记忆重构后续运行。

## 2. User-Visible End State

从用户视角，项目最终可见状态为：

- **入口与流程**：访客可直接进入公开 demo（或通过登录）进入 Daily Intelligence；工作流可从浏览、筛选、重点阅读到 Ask、Research、Export 无中断继续。
- **状态与恢复**：加载、空状态、部分成功、二次请求失败、重试、缓存回源失败等都有明确提示，不会误导为“全部成功/全部失败”。
- **阅读与标注**：文章上下文、列表位置、返回来源可保持；标注/笔记可在焦点移到编辑器后仍稳定提交；内容改动导致锚点变化时要么明确标记待确认，要么拒绝静默错绑。
- **交互一致性**：键盘、触控/触控等效、移动端导航、底部安全区域、焦点返回、模态层/菜单层级都可复用并可回退。
- **速度与稳定性**：关键页面在可接受阈值内可用，错误恢复不阻断任务；非关键体验故障不应拖垮主路径。
- **无障碍与降级**：`reduced-motion` 与高对比状态下仍可识别、可操作；错误与重试信息在视觉与语义上可感知。
- **品牌与视觉一致性**：延续 warm editorial 方向，但不以“装饰”代替任务语义。信息层级、动作层级、品牌识别与加载/错误状态应稳定一致。
- **交付与回滚**：可在 staging 路径上完成镜像发布、验证、回滚/恢复演练与记录；生产保持只读验证边界，除用户明确要求外不参与迭代突发变更。

## 3. Verified Baseline

快照：`2026-07-26`，基线主线 `origin/main=bdffb588`；当前候选为 `goal/m3-evidence-ledger`。
本文件只将已执行命令和保存的工件视为事实；候选修改须在同一分支上复跑相关验证后才可进入主线。

| Dimension | Current state | Evidence | Confidence | Missing evidence |
| --- | --- | --- | --- | --- |
| 仓库与执行入口 | 根 `AGENTS.md` 是唯一工程规则入口；CI 触发器集中在 `.github/workflows/*`。 | `rg --files AGENTS.md`、`cat .github/workflows/ci.yml`、当前 Git 历史 | High | 生产端完整上线证据 |
| 前后端栈 | `reader-web`(Next.js 16.2.11)、`api`(FastAPI)、`worker`(Python 3.13, uv)、`PostgreSQL + Compose + Caddy + Authelia`，匿名 demo 与生产边界已分离。 | `README.md`、`TECHNICAL.md`、`SPEC-CICD.md`、`infra/caddy/Caddyfile`、Compose 渲染 | High | 运行时容器外链路的当前小时级健康曲线 |
| API 正确性 | API 单元/集成测试与 PostgreSQL 条件合约已在 CI 通过；最新 migration 的降级/回放及隔离逻辑快照恢复均已验证；`ruff check` 通过。 | 本地：`uv ... python -m pytest tests -q`（219 pass）及 `ruff check .`；CI `30182799323`、`30212853939` artifact `db-postgres-snapshot-restore` | High | 真实部署数据量下的恢复时间与故障注入恢复链 |
| Worker 正确性 | `uv ... pytest`（worker）通过，含 4 个 PostgreSQL 条件跳过；`ruff check` 通过。 | 本次命令：`uv ... python -m pytest tests -q`（121 pass, 4 skipped）；`ruff check .`（pass） | High | 并发/恢复场景下长链路与重试边界 |
| Reader 回归 | `npm test`（193 pass）与 `npm run build` 成功；核心浏览器矩阵为 Chromium 55/55、Firefox 21/21、WebKit 21/21、iPhone WebKit 20/20；Scan/Focus/Keep 重排在 Chromium、Firefox、WebKit 的 320/375/390/768/1024/1280/1440px 均通过。 | `output/evidence/m2-cross-engine-core-2026-07-26.json`、`output/evidence/m2-responsive-widths-2026-07-26.json` | High | Firefox/WebKit 全量矩阵、跨引擎文本选区与更多输入法行为 |
| 前端测试/构建基线 | 构建与测试为绿色；未引入 lint 脚本。 | `apps/reader-web/package.json`（scripts）、`npm run build`、`npm run test` | High | 是否需要新增 `npm run lint` 为约束条件 |
| CI/CD 可验证性 | `ci.yml` 在主链路覆盖 API/worker/test/build/compose/deploy/checks 与 Trivy；当前分支最近有成功与失败运行。 | `.github/workflows/ci.yml`、`gh run list --limit 20`（最近成功与失败记录） | Medium | 最近成功运行中发布/回滚脚本是否与本版本完全一致 |
| 部署配置 | Compose base/staging/prod/edge 可渲染；`api-staging` 与 `web-staging`、`api-prod` 与 `web-prod` 可识别；`bash -n` 脚本与 deploy/迁移脚本语法通过。 | 本地命令：`docker compose ... config`（base/staging/prod/edge）、脚本语法检查 | High | 真正容器内 Metrics scrape 与回滚演练 |
| 授权与安全 | `git diff --check` 与脚本语法检查通过；`metrics` 内外边界脚本层已校验；`.env` 本地权限已整改。 | `python infra/scripts/check-metrics-boundary.py`（ok）、`bash -n` 脚本、`stat` 与 `chmod` 记录 | High | 生产域上 `401/403/404` 的长期回归与二用户隔离场景 |
| 依赖与供应链 | `npm audit --omit=dev` 为 0 高危/致命；Trivy secret/漏洞扫描有本地证据。 | `npm audit --omit=dev`、`output/security/frontend-dependency-remediation-2026-07-26.json`、`output/security/trivy-secret-scan-2026-07-26.json` | High（本地） | 生产镜像构建后的外部依赖漂移与锁定持续性 |
| 性能基线 | Web 有三缓存阶段五次基线；API/queue 有内存基线；DB 已在 disposable CI PostgreSQL 上以代表性 fixture 测量 4 类只读查询各 5 次；比较器支持 schema v1/v2 与显式 Web 指标，并在 CI 将当前候选与最近成功 `main` 的同环境基线以 3× 门限比较。 | Web：`evidence/web-performance-baseline-2026-07-26.json`；DB：CI run `30181950027` artifact `db-postgres-performance-baseline`（`MEASURED`，每查询 5 个非空样本，p95 0.48–0.51 ms）；CI `30183432804` 与 `30212853939` artifact `db-postgres-performance-comparison` | High（fixture） | 真实设备/慢网、写入负载与 deployment-like 负载 |
| 可访问性 | 已有静态可访问性快照与对比值，但仍存在低对比风险；A11Y 体系缺少完整自动化回归门。 | `output/performance/frontend-font-build-2026-07-26.json` 中的对比抽样、Playwright 现有样本 | Medium | 自动化 contrast/role/reduced-motion/reflow 全量栅格 |
| 可测验产品完整性 | M1 的三个小节各有独立证据；核心循环仍缺少完整状态矩阵（输入×来源×故障路径×恢复路径）。 | `output/evidence/m1-daily-partial-failure-2026-07-26.json`、`output/evidence/m1-reader-ask-retry-2026-07-26.json`、`output/evidence/m1-annotation-anchor-recovery-2026-07-26.json` | Medium | 完整 `A-02/A-03/A-07` 状态矩阵 |
| 运行时体验与交付边界 | 生产探针与回归并未作为本轮目标内动作；当前实践集中在 staging 与本地验证。 | 既有 `docs/goal-completion-evidence.md` 历史记载 + `gh run` 历史 | Medium | 生产实测与生产侧故障恢复完整证据 |

基线工件（建议固定期内持续更新）：

- `output/evidence-sha256.txt`
- `output/playwright/goal-baseline-2026-07-26/`
- `output/playwright/m0-fixtures-2026-07-26/`
- `output/playwright/m1-fonts-2026-07-26/`
- `output/playwright/m1-fonts-2026-07-26/`
- `output/performance/`
- `evidence/web-performance-baseline-2026-07-26.json`
- `output/security/`
- `output/anchor/annotation-anchor-contract-2026-07-26.json`
- `output/release/pr15-staging-proof-2026-07-26.json`
- `output/evidence/m1-annotation-anchor-recovery-2026-07-26.json`
- `output/evidence/m1-daily-partial-failure-2026-07-26.json`
- `output/evidence/m1-reader-ask-retry-2026-07-26.json`
- `output/evidence/m1-candidate-state-retry-2026-07-26.json`

## 4. Constraints and Non-Goals

### 必须保留

1. 维持现有架构：`reader-web + api + worker + postgres + caddy + miniflux + authelia`，不改造为新平台。
2. 保留 API 契约、session 模型、标注元数据兼容与匿名 demo 行为边界。
3. 保留 OpenAPI 与前端生成类型的同步机制（export + drift check）。
4. 不改动生产域名、数据库密码、secret、真实用户数据、SSH key 与凭证。
5. 生产发布链路为手工确认场景，当前任务默认在 staging 与本地可验证面内交付。

### 不做清单（N/A 或明确否决）

1. 不引入新语言栈/重写微服务边界；
2. 不进行无证据的“视觉变得更花哨”类优化（渐变、发光、过度阴影、粒子、无目的动效）；
3. 不进行全量依赖大升级，除非由明确 MUST 门禁要求和回归证据支持；
4. 不把“阻塞/待审批”写入核心流程；
5. 不把生产作为自动验证唯一边界；生产仅作为只读回归窗口。

## 5. Opportunity Map

| Area | Evidence-backed problem | User impact | Root-cause hypothesis | Confidence | Candidate intervention |
| --- | --- | --- | --- | --- | --- |
| 核心业务循环 | `A-02` 已有 Daily/Ask 两个局部故障场景，但完整循环仍缺完整矩阵。 | 用户可在局部故障后仍陷入不完整状态。 | 验收范围未覆盖跨模块、跨来源、跨故障类型组合。 | High | 建立统一“状态矩阵测试协议”，一次只覆盖一个失败维度。 |
| 标注锚点 | 已通过重复文本与模糊场景修复，但 inline markup、输入法变体、重试路径不完整。 | 错误归属或丢失笔记。 | 输入/渲染层对锚点恢复分支覆盖不完整。 | High | 增量增加最小失败场景 + 运行时显式提示，不进行静默回填。 |
| 可访问性 | 有历史对比值显示低对比风险，自动化仍不完整。 | 信息可见性下降，重读流程受阻。 | 缺少可复用 contrast + role + motion 自动回归门。 | High | 建立分层 A11Y 门（normal text contrast、landmarks、keyboard、reflow、reduced-motion）。 |
| 响应式与输入 | 现有 e2e 覆盖 Chromium 与多个断点，但 Firefox/WebKit、触控-输入矩阵未闭环。 | 长列表/导航/底部遮挡的边界风险仍可复发。 | 测试矩阵未形成覆盖率约束；优化停留在局部手工观察。 | Medium | 在可执行时间预算内补最小化 pairwise 矩阵（宽度×输入模式×关键场景）。 |
| 稳定性与恢复 | 已有失败场景存在，但没有统一恢复预算与重试上界。 | 用户会在同一失败面反复刷新，工作流中断。 | 缺少故障预算与回放脚本。 | High | 引入统一 `failure-budget` 与恢复时间上界（含重试次数、幂等行为）证据。 |
| 数据层与迁移 | API/worker 本地与 CI 已验证，PostgreSQL 条件测试有 skip，恢复/并发证据不足。 | 部署层面的行为可能与本地表现不一致。 | 条件性测试与真实 DB 场景未形成默认 gate。 | High | 将恢复/回退/并发场景作为 P0 门禁，保留最小可复现替代。 |
| 性能与可观测性 | DB 与路由 Web 指标仍为 `NEEDS_BASELINE`；现有 Web harness 使用旧 revision、每个样本新建 context（warmup 不会预热测量）、屏蔽 Service Worker、固定等待，并且只在零资源合成页上验证。 | 不易识别回归，且可能用伪 warm/cold 数字选择错误优化。 | harness 最初仅证明报告结构，未建模真实冷缓存、同-context 热缓存、PWA 缓存或应用就绪条件。 | High | 在性能调优前升级为可区分 `cold`/`warm-http-cache`/`service-worker-controlled` 的 schema-v2：热样本复用 context，使用有意义的 ready marker，记录当前 SHA/工具版本/资源分组/活动请求，并以有资源 fixture 验证缓存行为后再运行五次基线与预算。 |
| 发布与回滚 | staging 已有部署脚本，但回滚/forward 与清理演练未形成自动门禁闭环。 | 发布可验证但不可快速恢复。 | 发布链路中“证明”与“恢复动作”未统一到 GOAL 契约。 | Medium | 标准化 `deploy + proof + rollback + proof` 成一条里程碑链。 |
| 文档与可维护性 | 核心流程已有基础文档，但历史内容与新成果仍有重叠。 | 新成员可复现性不足。 | 证据和执行日志未始终同频。 | Medium | 每次里程碑关闭时更新 `PLANS.md`、`evidence-sha256` 与交接文档。 |
| 产品安全与隐私 | 会话与缓存边界有历史证据，但二用户/跨上下文隔离仍应持续加强。 | 上下文污染会直接影响信任。 | 运行时隔离验证未全部自动化。 | Medium | 两用户隔离脚本与 cache/fixture 比对常态化。 |
| SEO / 3D / 合规（当前不适用） | 与当前仓库目标无直接耦合。 | 与核心价值关系弱。 | 用户价值未体现于当前主循环。 | High | 标记为 `N/A`，仅在需求变更时复活。 |

## 6. Prioritized Scope

### P0：主目标必达

| Work | Impact | Confidence | Effort | Risk | Dependency | Why now |
| --- | --- | --- | --- | --- | --- | --- |
| 形成完整核心循环状态矩阵：Daily/Scan/Focus/Keep/Reader/Ask/Research 含加载、空、错误、重试、上下文恢复。 | Critical | High | Medium | Low | 当前 Playwright 与 Node 契约 | 先修正确性闭环再做任何外观优化。 |
| 完善标注恢复边界：重复文本、刷新、输入法输入、重试与会话分离。 | Critical | High | Medium | Medium | `output/evidence/m1-annotation-anchor-recovery...` | 错误归属是研究信任风险主因。 |
| 将 A-05/A-06（A11Y + 响应式/输入）升级为自动回归门。 | High | High | Medium | Low | 当前 e2e 样例 | 缺失门控会让可用性回归“看起来像样但不可靠”。 |
| 建立 P95/P50 与噪声阈值的非空性能基线（API、queue、Web、DB）。 | High | Medium | Medium | Medium | harness 脚本与历史报告 | 优化需要可比较指标防止空优化。 |
| 数据可靠性门：PostgreSQL 条件测试、migration replay、恢复脚本。 | High | High | High | Medium | CI postgres 服务 + 本地脚本 | API/worker 不能只依赖 memory 变体。 |
| Staging 回滚/恢复链条与证据固定。 | High | Medium | Medium | Medium | deploy/rollback/workflow | 发布成功不等于可恢复成功。 |

### 当前最高优先级 — M1.9b：Scan / Focus 列表状态与返回上下文的服务端真相

- **优先级与关系**：P0；承接 M1.9a 已提交并在 Chromium 证明的 Keep/`starred` empty、saved success、503→retry（`70f03234`）及 Review retry / Export download（`68ea97c8`），继续直接推进 A-02。当前只把已验证模块记为部分完成；Scan / Focus 的 loading、empty、error、retry、server-confirmed 与返回上下文仍未闭环。M1.7 的跨引擎文本选区仍为 A-06 `NEEDS_BASELINE`，不得倒推为完成。
- **优化目的**：使 Scan 与 Focus 用户能区分“服务器确认的有数据”“服务器确认的空集”“加载失败/可重试”，并在 retry、进入文章、浏览器返回或刷新后只呈现最新服务器结果与原始模块上下文；绝不把失败、旧数据或未加载伪装成“暂无文章”。
- **执行范围**：为 Scan 与 Focus 各建立最小、独立的 loading、empty、一次性失败→retry、success 和 article-return/refresh 状态路径；复用 Keep 的局部资源状态和 `ArticleList` error seam，不改变 URL、cursor、search、读进度、Miniflux/API 所有权或会话/PWA 缓存边界。fixture 仅用于客户端解释与恢复路径；若 Scan/Focus 的模块筛选语义、响应 shape 或状态写入需要变更，必须以 API 契约测试补证，不能由 fixture 代替。
- **验收标准**：Scan 与 Focus 每一目标状态均有互斥 UI；服务器失败时无空状态、过时 success 或跨模块内容冒充当前结果；retry 仅重试失败资源并成功清除错误；empty 仅在成功空响应时出现；文章进入后 Back/refresh 恢复正确的 `module/sort/lang/cursor` 与可见列表结果。已验证的 Keep/Review/Export slice 保留为 A-02 部分证据，不因扩展 Scan/Focus 而回归。
- **验证方法**：先失败的 Node/Playwright 场景分别覆盖 Scan 和 Focus 的 empty、503→retry、server success 与 article-return/refresh；运行相关 Reader Node 测试、完整 Chromium suite、production build、`git diff --check`。随后在 Firefox/WebKit/iPhone WebKit 最小核心矩阵复跑共享的列表恢复路径；记录 module、服务器响应、URL、可见状态、retry 次数、恢复后的 article ID 和命令 exit。发生 API 形状/筛选变更时追加 API pytest、Ruff、OpenAPI/生成类型漂移门。
- **方案取舍**：一次只增加一个模块与一个失败维度，不引入全局状态框架、不以空数组复用 loading/error、不用乐观本地过滤伪造服务端结果；先在既有确定性 fixture 上锁定状态解释，再在 API 层确认证明需要的语义。
- **风险与回滚**：低到中等的 fixture/URL 状态竞争风险。Scan 与 Focus 独立提交、独立回退；任何只在 fixture 中成立的结论保持 `IN_PROGRESS`，直至相应 API 契约与跨引擎恢复证据补齐。

### P0 后继任务（M1.9 验证后）— 原子文章状态与候选不变量

- **优先级与关系**：P0；在 M1.9 的列表状态矩阵收口后开始。它将 M1.4 已验证的“服务端确认状态”延伸到 A-08/A-10 的数据层真实并发语义，保护 A-02 的 Keep/candidate 主循环；A-05/A-06 的窄屏、对比度与 motion 自动门持续保留在 MUST 验收，后续按影响/证据重新排序，不因本次状态矩阵切片被取消。
- **优化目的**：消除 PATCH 风格 article-state 写入的 read-modify-write 丢更新，并让 `project ⇒ saved` 成为所有写入者都无法绕过的存储层不变量。
- **执行范围**：将 repository 写入变为单一原子操作，只更新请求明确携带的字段；在同一操作内处理 `saved=false → project=false` 与 `project=true` 的合法性。增加可回退 migration，先检测历史无效行并可见失败，绝不静默修复或删除数据；添加等价于 `NOT project OR saved` 的数据库约束。保留既有 request/response/OpenAPI 形状与 Miniflux 边界。
- **方案取舍**：允许使用行锁加局部更新，或使用经测试的条件式 PostgreSQL upsert；选择更小、可审计且能证明无丢更新的方案。不得用前端重试、乐观更新或仅 memory 测试替代原子性。
- **验收标准**：并发 `status=read` 与 `saved=true` 后两项均保留；`project=true` 与 `saved=false` 竞争后不存在 `project=true, saved=false` 行；直接无效 insert/update 被数据库拒绝；API 返回的最终状态与持久化状态一致。
- **验证方法**：新增 memory 行为回归及两个 PostgreSQL 实例的并发集成测试，覆盖 claim/lock 交错、约束拒绝与 migration preflight；运行 API pytest、Ruff、Alembic upgrade、OpenAPI/生成客户端漂移检查和相关 Reader state 场景。记录精确 SHA、数据库摘要、并发步骤和回滚 revision；任何旧数据异常保持可见失败而非自动改写。
- **风险与回滚**：中等迁移风险。该 slice 独立提交；若 preflight 或 PostgreSQL 行为不成立，revert migration/repository slice，保留 M1.4 的前端失败证据但不得宣称数据层完成。

### P1：稳定性放大（低风险）

| Work | Impact | Confidence | Effort | Risk | Dependency | Why now |
| --- | --- | --- | --- | --- | --- | --- |
| 建立失败预算与恢复时间窗（retry timeout/fallback/冪等） | High | Medium | Low | Low | P0 状态矩阵 | 降低隐性错误成本。 |
| 发布前文档与执行一致性收敛（PLANS、学习笔记、runbook） | Medium | High | Low | Low | 既有 runbook | 降低交接成本与误操作风险。 |
| 分层可维护性：仅对当前已验证问题提取失败定位 seam。 | Medium | High | Medium | Medium | 变更热区 | 防止无关重构。 |

### P2：体验精修（可验证价值后）

| Work | Impact | Confidence | Effort | Risk | Dependency | Why now |
| --- | --- | --- | --- | --- | --- | --- |
| 在验收通过后优化视觉层次与信息节奏（品牌一致、密度、动效目的性） | Medium | Medium | Medium | Medium | P0/P1 完成 | 防止影响主逻辑。 |
| 增加受控的失败美学保护（保持动效不影响理解） | Medium | Medium | Low | Low | A05 结果 | 仅在可测的前提下优化。 |

### Deferred / N/A

- 全站 3D、复杂动画体系；
- SEO/外部公域内容分发；
- 大规模依赖升级；
- 合规认证类专项（当前无证据显示是当前用户核心需求）。

## 7. Acceptance Matrix

| ID | Outcome | Priority | Baseline | Target | Verification command or procedure | Evidence artifact | Pass condition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-01 | 基线复现与可追溯 | MUST | 未形成“一个 SHA 对应完整基线清单” | 形成完整 evidence manifest 与哈希验证 | `shasum -a 256 -c output/evidence-sha256.txt` + `git rev-parse HEAD` + `git status --short` + 关键命令复跑 | `output/evidence-sha256.txt` | 关键命令在同一工作树版本上可复现；`git diff --check` 通过；证据文件和状态可审计 |
| A-02 | 完整核心循环状态正确性 | MUST | 已有 Daily 与 Ask 的单场景通过 | 完整覆盖核心循环的状态矩阵 | `npm run test:e2e`（含新规约场景）+ `npm test` | `output/playwright/...`、`output/evidence/*.json` | 每个状态分支都有可复现的成功/失败/重试/恢复断言；无隐藏上下文丢失 |
| A-03 | 标注与引用可信性 | MUST | 部分修复（重复文本、内容刷新） | 覆盖 inline markup、输入法/多输入源、会话切换与重试 | `node --test --import tsx src/lib/articles/*.test.ts` + 关键 Playwright 场景 | `output/evidence/m1-annotation-anchor-recovery-2026-07-26.json` 及新增同类证据 | 重建/错位后无静默误绑；无法确定时显式保留警告且不丢数据 |
| A-04 | 权限与隐私边界 | MUST | 403/200 边界已见证 | 两用户隔离、Admin 分离、secret 不入证据 | API auth tests + 两用户浏览器路径 + `check-metrics-boundary` + `bash -n` | `output/security/*`、`output/playwright/*` | 非授权请求不返回越权信息；用户状态切换后无交叉残留 |
| A-05 | 无障碍可用性 | MUST | 仅局部样本可见，自动化未闭环 | 通过 contrast/role/键盘/reflow/reduced-motion 基线 | Playwright accessibility + 自建 contrast 验证 | `output/goal-evidence.md` 后续新增条目 | 必要交互节点在 required contrast 与键盘路径下可用 |
| A-06 | 响应式与跨输入 | MUST | 已有 Chromium 多断点覆盖 | 加入跨浏览器 + touch-equivalent + 重排边界场景 | Playwright 断点矩阵（375/390/768/1024/1280/1440，Chromium/WebKit/Firefox）+ 固定断言 | `output/playwright/*` | 无水平溢出、可操作、焦点返回正确、无关键入口丢失 |
| A-07 | 用户可见质量（状态语言） | MUST | 部分场景通过，rubric 未闭环 | 在固定夹具上执行 rubric 达到可接受基线 | screenshot 套件 + 人工复核脚本输出 + 评分表 | `output/playwright/m1-fonts-...` 等 | 核心页面在固定场景下达到最低分阈值，无“装饰补丁式”提升 |
| A-08 | API 与数据可靠性 | MUST | API/worker 本地通过；最新 migration 已降级/回放，隔离 PostgreSQL 逻辑快照已恢复并核对版本与 fixture 记录 | migration + PG 条件测试 + 恢复回滚证明 | `uv ... pytest`（PG 条件）+ Alembic `downgrade -1`、`upgrade head`、`current --check-heads` + CI `Verify disposable PostgreSQL snapshot restore` + 后续 rollback replay | CI `30182799323`、CI `30212853939` artifact `db-postgres-snapshot-restore` + 后续 rollback evidence | 条件测试、migration replay、恢复后 migration/fixture 断言与 rollback replay 一致；无未解释 skip |
| A-09 | 性能与稳定基线 | MUST | Web、API/queue 及 CI PostgreSQL 都有五次基线；schema-v1/v2 比较器已验证，并在 CI 对最近成功 `main` 基线执行同环境 3× 阈值比较 | 固定 Web 三缓存阶段、CI DB fixture 和回归阈值 | Web 命令 + CI `Run PostgreSQL performance baseline` + `check-performance-baseline.py --max-regression 3` | Web evidence、CI `30181950027` artifact `db-postgres-performance-baseline`、CI `30183432804`/`30212853939` artifact `db-postgres-performance-comparison` | 每路由/阶段有 5 个非空样本；SW 阶段全部受控；无浏览器/HTTP 错误；DB 基线可复现，且同环境候选比较不超过 3× 门限 |
| A-10 | 恢复与韧性 | MUST | PostgreSQL 过期租约可由替代 worker 恢复；CI 已在存在竞争任务时完成 5 次 `running → queued → running → succeeded` 测量，median 5.614 ms、p95 7.956 ms，并保留 content-free recovery 日志 | 保留可重复恢复预算，并补齐数据库暂不可用、锁竞争、超时与重试耗尽的错误分类和降级证据 | PostgreSQL lease-recovery/竞争测试 + `queue-recovery-baseline.py` + `worker stale lease recovery` 日志断言 + 后续故障注入 | CI `30213382395`、`30278849416`、`30284291417` artifact `queue-postgres-recovery-baseline` + 后续故障矩阵 | 已覆盖故障可在预算内回到已知状态；不重复完成、不沉默损坏数据、不泄露 payload |
| A-11 | 供应链和密钥边界 | MUST | Trivy 与 npm audit 本地绿色（高危/致命） | 复核 CI 高危致命阈值、secret redaction 与锁文件治理 | CI/本地同参数扫描 | `output/security/frontend-dependency-remediation-2026-07-26.json`、`output/security/trivy-secret-scan-2026-07-26.json` | 无高危/致命，扫描命令参数透明且与 CI 一致 |
| A-12 | staging 发布与回滚闭环 | MUST | staging 已自动部署 `2ec6cd28`，回滚至已发布 `98d06a42`，再前进重放当前镜像；三步均通过；GHCR cleanup 的 repository-scoped dry-run 已完成多架构校验且无删除 | 在单一最终 SHA 上完成 deploy、rollback、重放、验证 | CI `30279882267` + `rollback.yml` run `30280699086` + `deploy-staging.yml` run `30280839157` + `ghcr-cleanup.yml dry_run=true` | GitHub Actions `30279882267`、`30280699086`、`30280839157`、`30282030908` | staging 可重复部署、回滚、再部署且各路由状态可重放；cleanup rehearsal 不执行删除且无多架构校验错误 |
| A-13 | 文档与执行可持续性 | MUST | 目录有基础文档，日志仍需统一 | 进展、决策、失败与下一步统一保存在 GOAL/PLANS/evidence | 交接复核脚本或手动核对：`PLANS` 与 `docs/session-handoff` 关联 | `PLANS.md`、`docs/session-handoff.md`、`docs/learning-notes.md` | 任何执行者可按文件继续，不依赖口头记忆 |
| A-14 | 设计可识别性（非装饰性） | SHOULD | 有部分统一视觉修复 | 不采用装饰性技巧，按任务语义改进状态表达 | 视觉对比矩阵+rubric审查 | 设计验收记录 | 不以渐变/发光/粒子替代信息结构提升分数 |
| A-15 | 外部服务与成本安全 | MUST | Ask 使用 Mock/Fixture 可验证 | 保证真实接口在预算/超时/禁用场景下安全降级 | Provider contract + Mock 回放 + caps/timeout 测试 | `output/evidence/*` | 无真实密钥消费；无法复现真实成本时不改用其作为必须验收 |

## 8. Quality and Delight Rubric

每个维度为 0–5 分，需用固定夹具+可复核脚本评估。

| Dimension | 0–1 failure | 3 acceptable | 4 excellent | 5 exceptional | Evidence |
| --- | --- | --- | --- | --- | --- |
| 产品任务完成 | 关键流程经常卡住或丢上下文。 | 流程能走完，需少量手动重试。 | 失败与成功场景均可恢复，路径清晰。 | 复杂错误下也能高置信恢复。 | A-02 路径矩阵结果 |
| 信息层级 | 信息乱序、按钮冲突、状态不清。 | 主要操作有序可见。 | 工作流入口、结果、下一步清晰。 | 层级在不同状态下自动稳定。 | Playwright 层级截图与 DOM 断言 |
| 交互清晰度 | 键盘/手势行为被吞，焦点丢失。 | 常规交互可用。 | 键盘、触控、返回焦点一致。 | 复杂输入下仍可预测。 | `is*`/focus/快捷键断言+e2e |
| 视觉一致性 | 全局样式风格不一致。 | 核心区域可用。 | 同一语义组件风格一致。 | 品牌识别从组件行为中可感知。 | 固定截图比对与组件快照 |
| 品牌辨识度 | 使用通用模板视觉，无研究语义。 | 保留现有 warm 识别。 | 标题/阅读/证据链形成统一风格。 | 一眼可见是研究/证据导向产品。 | 截图与文本节奏审计 |
| 目的性动效 | 动效与任务冲突或无价值。 | 减少无效动效。 | 动效说明状态变化且可降级。 | 动效不增加认知负担且可复用。 | 采样 trace 与手工审阅 |
| 3D/Narrative | 与产品目标无关。 | N/A（不引入） | N/A（不引入） | 如果未来引入则需证据证明收益与无负担 | 仅当 N/A 解除时增加证据 |
| 性能与无障碍 | 关键路径卡顿/不可见。 | 加载可进入，核心动作可达。 | 预算内稳定，关键错误可复原。 | 在低端/慢网也有可预测体验。 | `output/performance/*` + 基线回归 |
| 错误与边界处理 | 错误被吞掉或误导。 | 基础错误可见。 | 可重试、可诊断、无数据隐患。 | 可重放恢复方案与错误归类完整。 | A-02/A-10 证据链 |
| 代码可维护性 | 大块改动且难回退。 | 修改范围可界定。 | 失败-修复-回归路径清楚。 | 每次迭代 1–2 个失败门可回退。 | Diff 拓扑与里程碑回放日志 |

## 9. Milestones and Checkpoints

### M0 — 基线与评估基础设施（首要）

- **目标**：把当前仓库状态、验证命令与证据链固定为可复跑模板。
- **输入**：`AGENTS.md`、`GOAL.md`（本版）、`PLANS.md`、当前证据目录。
- **范围**：基线命令校验、证据清单更新、`README/PLANS` 一致性对齐。
- **验证**：A-01、A-11、脚本语法、Compose 渲染。
- **成果**：可从 `evidence-sha256` 与输出目录复现。
- **回滚**：仅保留只读证据变更，未改业务。
- **更新**：`PLANS.md`、`output/evidence-sha256.txt`、`docs/learning-notes.md`。

### M1 — 核心循环闭环（基础质量）

- **目标**：核心循环在状态、标注、重试方面闭环；消除“静默错绑/静默丢上下文”。
- **输入**：现有 M1 证据、fixture。
- **范围**：最小失败场景修复 + 对应 Node + e2e。
- **验证**：A-02、A-03、A-04。
- **成果**：核心流程中任一失败场景均可明确恢复。
- **回滚**：逐场景 revert；任何新增状态分支独立可回退。

### M2 — 可用性与韧性门禁

- **目标**：A11Y、响应式、输入、reduced-motion、恢复预算成为稳定验收门。
- **输入**：M1 已修复的关键行为。
- **范围**：最小新增断言与对照脚本。
- **验证**：A-05、A-06、A-10。
- **成果**：不同设备/输入下不再出现关键路径阻塞。
- **回滚**：把样式/输入修复与行为修复分开提交。

### M3 — 数据与性能稳定闭环

- **目标**：将数据库/队列/API/web 的可复测基线转为量化门禁。
- **输入**：现有 harness 与脚本。
- **范围**：五次重复、差异阈值、异常预算。
- **验证**：A-08、A-09、A-10。
- **成果**：有可比较性能与恢复预算。
- **回滚**：未满足收益阈值则撤销优化，保留最小行为修复。

### M4 — 发布可恢复闭环

- **目标**：把发布、回滚、清理演练纳入同一里程碑。
- **输入**：M0-M3 的 `A-01`～`A-10` 结果。
- **范围**：staging/release/rollback 证据固定。
- **验证**：A-12、A-13。
- **成果**：发布与恢复成为独立可审计流程。
- **回滚**：保留上一个稳定 SHA 与镜像标签，避免破坏运行状态。

### M5 — 完成闭环与手交接

- **目标**：输出可无人接力的交接与继续执行规则。
- **输入**：全部通过的 MUST 门。
- **范围**：决策日志、风险登记、下一动作。
- **验证**：A-01 全部通过、Success 条件齐全、`docs/session-handoff.md` 更新。
- **成果**：新执行者只需 GOAL+PLANS+evidence 即可继续。

## 10. Execution Protocol

1. 每个迭代先执行 baseline（A-01），再改动一个高价值瓶颈。
2. 任何一次失败优先缩小到最小复现；若复现通过，先修复该面，再运行相关验证。
3. 无需等待人工批准，优先采用替代资源与 Mock；缺口标记为 `NEEDS_BASELINE`。
4. 每个里程碑结束后产出 1) 新证据列表 2) 回滚点 3) `git diff --check` 结果。
5. 关键决策应有“为什么不做更复杂改动”的证据。

### 自动决策规则

- 在满足约束且同功能收益相当时，优先选：更小 diff、边界更小、无外部依赖、性能更稳定、回滚更容易的方案。
- 任何“为了更快而做的重构”必须能映射到一个 MUST/SHOULD 门禁。
- 对外部不可用的场景继续推进替代项，不新增阻塞状态。
- 不能为了“看上去好”而牺牲可验证状态。

### 失败恢复与回滚

- 发现连续 2 次以上无进展失败时，撤销当前实验改动，回到最近可验证 checkpoint。
- 出现性能回退且无收益时，撤销性能优化并回归到上一个可复验基线。
- 发生跨服务/外部依赖缺失时，记录失败原因并切换到最小替代路径，不阻塞后续非外部门禁。

### 持续进化

- 里程碑结束后按“影响→证据→失败率”排序修订下一轮工作。
- 对新发现问题仅当与核心目标相关时进入下一轮。
- 不新增新技术栈，只在收益已验证且可回退时引入辅助工具。

## 11. Progress and Evidence

`PLANS.md` 当前建议字段（与该合同一致）：

- **Current candidate**：`goal/m1-annotation-input-continuity @ 1a41edc4`（base `origin/main @ 97cd28e1`）；M1.7、M1.9a 与 A-05/A-07/A-15 的增量 slice 均已提交，尚待合并。
- **Current milestone**：M1.7（annotation/input continuity）已完成。M1.9a 已完成 Keep/`starred` empty、saved success、503→retry 和 Review/Export 的可见恢复 slice；当前进入 M1.9b，收口 Scan / Focus 列表状态及文章返回上下文。
- **Last green checkpoint**：M1.7 的完整 gate 为 Reader Node 194/194、production build、fresh-server Chromium 70 passed。其后 M1.9a 记录 Chromium 73/75，A-05 语义/键盘记录 Chromium 77，A-15 Ask abort 记录 Chromium 78；跨引擎核心扩至 Firefox 35/35、WebKit 35/35、iPhone WebKit 29/29。当前没有与 `1a41edc4` 对应的完整 Node/build 重跑记录，故不得把这些增量外推为全量 gate 通过。
- **Current validation**：A-08 已有 PostgreSQL CI 合约、latest downgrade/replay 和隔离逻辑快照恢复；A-09 已有 Web、DB、比较器和 CI 阈值门；A-10 已有真实 PostgreSQL lease recovery、竞争任务隔离、五样本恢复预算和 content-free 运行时日志；A-12 已通过 staging rollback-forward 与 cleanup rehearsal。A-02/A-03/A-04/A-05/A-06/A-08/A-09/A-10/A-13/A-15 仍持续进行中。
- **Before/after metrics**：
  - Web：冷启动资源中位数 home/all 为 627852/624866 B；HTTP-cache warm 为 5081/2095 B；Service Worker controlled 均为 true（本机 E2E fixture，非真实网络 SLA）
  - DB：CI PostgreSQL fixture 的 latest/search/ready-job/due-review p95 分别为 0.510/0.496/0.484/0.506 ms；每项 5 个非空样本（CI run `30181950027`）
  - Queue recovery：CI PostgreSQL 五样本 median 5.614 ms、p95 7.956 ms、min 5.516 ms、max 7.956 ms；各样本均完成 `running → queued → running → succeeded`（CI `30284291417`）
  - baseline 入口：`apps/api` 219/0，`apps/worker` 121+4skipped，`reader-web` 194
  - e2e：Chromium 79/79；Firefox 44/44；WebKit 43/43；iPhone WebKit 29/29（cross-engine grep 扩展后，非各引擎全量）
  - 漏洞：生产依赖高危=0（本地），`npm audit --omit=dev`
- **Current experiment**：M1.9a 已在 Chromium 75 完成并入提交：Keep/`starred` empty、saved success、503→retry，及 Review retry / Export download；A-05 语义+Tab audit、A-07 状态语言 non-contradiction 与 A-15 Ask abort 已有后续小型 Chromium 证据。M1.9b（Scan / Focus）尚未开始验证，仍为 `IN_PROGRESS`。
- **Recovery point**：当前 code/goal checkpoint 为 `1a41edc4`；完整 Reader Node/build checkpoint 仍为 `a6df7919`；主线 `39422aee25f21adaaa2682e8ada15badc82df57c`；应用回滚点仍为已验证的 `sha-98d06a4`，最近 staging 候选为 `sha-db574ab`。
- **Missing external evidence**：与当前 HEAD 对应的完整 Node/build/Chromium gate、Firefox/WebKit 全量、跨引擎文本选区和列表恢复、真实 PostgreSQL 写入/route 性能，以及数据库暂不可用/锁竞争/超时/重试耗尽故障矩阵。
- **Known risks**：核心状态矩阵仍未闭环；fixture 成功不等价于 API 模块筛选语义已验证；新 A-05/A-07/A-15 场景只有增量证据而非完整 gate；跨引擎选区自动化尚不稳定；恢复预算仅覆盖过期租约；GHCR 真实删除未演练并继续采用显式非破坏性 dry-run 策略。
- **Next action**：为 Scan / Focus 先建立并验证 empty、503→retry、server success、article-return/refresh 的最小状态矩阵；随后重跑当前候选的 Reader Node、production build 和完整 Chromium gate，再扩展跨引擎列表恢复矩阵。

## 12. Decision and Change Log

| Timestamp | Decision | Evidence and effect |
| --- | --- | --- |
| 2026-07-26 | 用“单一核心目标”替代“全方面优化清单”。 | 约束到核心循环、标注安全、恢复、发布边界。 |
| 2026-07-26 | 将缺失外部服务定义为 `NEEDS_BASELINE` 而非阻塞。 | 防止人工审批依赖；任务可继续在替代链下执行。 |
| 2026-07-26 | 冻结可见度：以 Playwright/Node 事实为验收主线，禁止凭主观审美提前宣告通过。 | A-07 需 rubric 证明，不可用视觉印象替代。 |
| 2026-07-26 | 维持生产只读边界，staging 作为主发布与验证面。 | 保障核心目标不引入不可控生产风险。 |
| 2026-07-26 | Web 性能工件升级为 schema v2，并按 cold / warm HTTP cache / Service Worker controlled 分离上下文。 | 避免把每次新建上下文的样本误称为 warm；每个测量页面以 `.workbench` 为就绪标记、关闭页面防止跨样本泄漏，并记录 SW 控制和资源类型传输。 |
| 2026-07-26 | CI PostgreSQL baseline 使用幂等代表性 fixture，而非依赖测试残留。 | CI run `30181950027` artifact 证明 4 类查询各有 5 个非空样本；fixture 仅存在 disposable CI service，不触及 staging/production。 |
| 2026-07-26 | 性能比较器显式选择延迟指标，并支持 schema v1 与 v2。 | `check-performance-baseline.py` 的 API/queue/Web 自比较通过，3.01 倍 API 合成回归以 exit 1 失败；未将跨环境比较误报为通过。 |
| 2026-07-26 | 最新 Alembic revision 在 CI 固定执行降级与回放。 | CI `30182799323` 成功执行 `downgrade -1 → upgrade head → current --check-heads`，再完成全量质量、镜像与 staging 链。 |
| 2026-07-27 | CI 固定从最近成功 `main` 下载 DB baseline，并以 3× 上限比较候选。 | PR #31 CI `30183432804` 及后续 CI `30212853939` 成功产出 `db-postgres-performance-comparison`；跨环境数据仍不得作为通过证据。 |
| 2026-07-27 | CI 在 disposable PostgreSQL 中完成逻辑快照恢复验证。 | CI `30212853939` artifact `db-postgres-snapshot-restore` 恢复到隔离数据库，并断言 revision `0011_project_requires_saved`、fixture article 与 annotation；不触及 staging/production。 |
| 2026-07-27 | CI 在 disposable PostgreSQL 中验证 worker 租约恢复由新 worker 完成。 | CI `30213382395` 的 `test_postgres_queue_state_machine_sql` 使过期 `running` job 退避为 `queued`，再由 `worker-after-restart` claim 并成功结束；未改变生产重试策略。 |
| 2026-07-27 | Worker 在回收过期租约时记录 content-free 关联事件。 | CI `30278849416` 验证 `worker stale lease recovery` 包含 worker、recovered_count 与 lease_seconds，不记录 job payload 或错误正文。 |
| 2026-07-27 | staging 已完成不可变镜像 rollback-forward 演练。 | 当前 SHA CI `30279882267` 成功部署；`30280699086` 回滚到 `sha-98d06a4` 成功；`30280839157` 将 `sha-2ec6cd2` 重放到 staging 并通过 runtime proof。 |
| 2026-07-27 | GHCR cleanup 已以 repository-scoped package 路径完成非破坏性演练。 | `30281085629` 的 404 证明旧包名遗漏 `reno_rss/` 前缀；修复后 `30282030908` 在 dry-run 模式枚举三个包、保留 15 个 tagged 版本、验证多架构 manifest，且不删除版本。 |
| 2026-07-28 | 队列恢复基线不得假设 disposable CI 数据库中没有其他 ready job。 | 初始 CI `30282641983` 产出 `RuntimeError`；test-only CI `30284173132` 用优先级 1 的竞争 job 稳定复现失败，证明普通优先级 synthetic job 会误领其他工作。 |
| 2026-07-28 | synthetic recovery job 使用 PostgreSQL INTEGER 最大优先级，但继续走生产 claim/reclaim/complete 状态机。 | PR #40 CI `30284291417` 的竞争回归与五样本 baseline 均通过，竞争 job 保持 queued；artifact median 5.614 ms、p95 7.956 ms，完整质量、镜像和 staging 链绿色。 |
| 2026-07-26 | 重新编制 GOAL 并以证据优先格式输出。 | 本次提交：清晰主目标、门禁、基线、自动决策与停机条件。 |
| 2026-07-26 | 状态写入失败必须显式可重试，并以服务端返回状态收敛界面。 | M1.4 Chromium fixture 证明 503 不丢 Reader 上下文，重试后候选状态通过详情刷新确认。 |
| 2026-07-26 | 用最小跨引擎核心矩阵替代 Chromium 单引擎断言，并让 CI 安装 Chromium、Firefox、WebKit。 | Chromium 55/55、Firefox 21/21、WebKit 21/21、iPhone WebKit 20/20；跨引擎选区与 1024/1280 不在该子集内，仍为 `IN_PROGRESS`。 |
| 2026-07-26 | 将 Scan/Focus/Keep 重排门扩展至 390、1024、1280px。 | Chromium、Firefox、WebKit 各 21/21；断言覆盖无水平溢出、文章可进入和关键操作可见，跨引擎选区仍为 `IN_PROGRESS`。 |
| 2026-07-27 | M1.7：IME composition 期间 Escape 仅取消输入法组合，不清除选区锚点。 | `isSelectionDismissEvent` 检查 `event.isComposing`；Node test-first failure + stash-reverted e2e failure 证明缺陷；修复后 focused 6/6、Reader 194/194、build、Chromium 65 passed。证据：`output/evidence/m1-ime-selection-continuity-2026-07-27.json`。 |
| 2026-07-27 | M1.7：标注保存 503 必须显式可重试，且锚点必须从文章内容文本构建。 | 内联错误横幅 + retry 闭包保留选区；`anchorContentRef` 使锚点从 `.focusContent` 构建而非含 UI 标签的 `<article>`；e2e 先失败（prefix 含 UI 文本，start 158）后通过。Chromium 67 passed。证据：`output/evidence/m1-annotation-save-retry-2026-07-27.json`。 |
| 2026-07-27 | M1.7：会话切换后标注必须按用户隔离。 | e2e server 新增 per-user annotation storage（`userAnnotations` Map）；用户 A 创建标注后切换到用户 B，B 只见 fixture 标注不见 A 的创建；Chromium 69 passed。证据：`output/evidence/m1-session-switch-isolation-2026-07-27.json`。 |
| 2026-07-27 | M1.8：触控保存与触控选区必须分开取证。 | 工作树的 `touch selection save` 仅以程序化 range + `mouseup` 建立选区，再用 `tap()` 保存；它可证明保存按钮的 touch-equivalent 路径，不可证明原生触控文本选择。A-03/A-06 维持 Pending，最高优先级调整为建立或明确限定真实 `touchend → settled anchor → save` 事件链。 |
| 2026-07-27 | M1.9a：M1.7 证据收口后，核心列表状态矩阵优先于新增视觉优化。 | `70f03234` 的 Keep/`starred` empty、saved success、503→retry 以及 `68ea97c8` 的 Review retry / Export download 已在 Chromium 73/75 验证，并写入哈希 evidence。fixture 结论仍须在需要时由 API 契约补证，不能外推为全模块或服务端完成。 |
| 2026-07-27 | M1.9b：收口 Scan / Focus 的状态和返回上下文，再扩大已验证边界。 | 当前最新提交 `1a41edc4` 还加入 A-05 semantic/Tab、A-07 state-language 和 A-15 abort 的小型 Chromium 覆盖（至 78），但当前 HEAD 没有完整 Node/build gate。最高优先级保持 A-02，先以 Scan / Focus 的 empty、503→retry、success、article-return/refresh 建立最小可回退矩阵。 |

## 13. Stop and Escalation Conditions

### Success

- 所有 MUST 条目（A-01、A-02、A-03、A-04、A-05、A-06、A-08、A-09、A-10、A-11、A-12、A-13、A-15）在单一提交 SHA 上为 PASS；
- `docs/session-handoff.md`、`PLANS.md`、`GOAL.md` 与证据清单一致；
- 交付证明包含：命令、日志、截图、哈希、回滚点；
- 无高危安全回归与未说明用户体验回归；
- 该版本可在 staging 路径执行一次可复现的部署-验证-回滚脚本。

### Safe continuation

- 任一 MUST 未通过时不停止执行；改为回到当前里程碑起点并只做最小闭环修复。
- 当外部依赖连续缺失时，切换到本地替代链并记录缺口，待外部恢复后再复跑。
- 当某项实验两次连续失败（同证据框架下）时，撤销该实验并转向下一低风险候选。
- 当验证出现隐性噪声而非功能回归时，先复现并固定随机种子后再判定。

### External-risk handling (not a stop condition)

- 真实数据、生产权限或密钥不可用时，使用 disposable 数据库、fixture、Mock 或适配层完成等价验证，并将差异列为 `NEEDS_BASELINE`；不得把该缺口改写为人工审批或恢复依赖。
- `AGENTS.md` 与仓库关键文档不一致时，以 AGENTS 和本合同的保守兼容解释继续，修正文档漂移并记录决策。

# 2026-07-08 全项目优化施工轮(B1–B7)——扫描定稿,交 Codex 逐批执行

> **历史/设计计划警告（2026-08）**：本文不是现行部署 runbook。文中的旧 workflow、SSH、GHCR 或 `infra/scripts/*` 示例禁止直接执行；当前手工入口是 request-only，边界以根目录 `SPEC-CICD.md`、`SPEC-CICD.zh-CN.md` 和 `docs/runbooks/` 为准。

> **来源**:三个并行域扫描(后端 api+worker / 前端 reader-web / 基建 compose+CI+docs+安全)× 批次级技术设计,全部发现与设计前提已对 HEAD 逐条核实(含四项关键声明二次抽查)。
> **基线**:PR #13(MiniMax 生成参数 + `<think>` 剥离加固)**先合并**,本轮所有批次基于其合并后的 `main`。本轮多文件与 #13 重叠(ask.py / config.py / llm.py / compose base / deploy.sh / .env.example)——规格一律以 HEAD 实际代码为准,不以旧文档为准。
> **用户拍板**:范围 = 新发现 + 路线图 F 批 + E2 批全部编入一轮;G(调度器)不进本轮但本轮补齐其缺的门槛件(B1);**一批一 PR**(回归治理惯例,上轮单 PR 是例外)。
> **承接**:`2026-07-04-post-v04-automation-roadmap.md`(F/E2/G/I 原文,本文档对其有前提修正,见 §前提修正)、`2026-06-28-security-rate-limit-cost-spec.md`(T1–T5 已全部落地;本轮 B1 = worker 侧预算缺件)。

---

## ⛔ 硬护栏(全轮适用,违反即判失败)

1. **白名单纪律**:每批 PR 的 `git diff --stat` 只许出现该批白名单文件;出现别的 = 失败。不顺手重构、不重排无关代码(AGENTS.md:最简足够改动 + 精确编辑)。
2. **安全不变量零触碰**:`sanitizeArticleHtml()`、`<think>` 剥离 + Markdown-only agent 输出、staging 匿名 demo 边界(`AI_READER_ANONYMOUS_DEMO` 默认 `False`,prod fail-closed 401)、admin `require_admin` 403、不提交任何真实 secrets。smoke-test 三断言(prod 401 / staging 200 / admin 403)每批不回归。
3. **API 形状变更(B2/B3)必须同 PR 再生** `apps/api/openapi.json` + `apps/reader-web/src/lib/api/generated/schema.ts`——CI 有 `git diff --exit-code` 回归门(ci.yml:66),漏再生必红。
4. **B7 特殊约束**:非测试文件的 diff 只允许注释;出现任何行为变更 = 失败。
5. **B2 部署前置**:CSRF fail-closed 上 prod 前必须完成 OPS-2(核对 VPS `.env` 的 `DOMAIN`)。
6. compose 改动(B1/B5)必须四 overlay config 校验全过(命令见下);`git diff --check` 每批必过。
7. 每批 PR 描述附统一验证命令的执行结果。

---

## 统一验证命令

```bash
# api / worker(改到哪侧跑哪侧;B1/B2/B3/B7 双侧都跑)
cd apps/api    && uv run --isolated --with-editable . --extra dev python -m pytest tests -q \
               && uv run --isolated --with-editable . --extra dev ruff check .
cd apps/worker && uv run --isolated --with-editable . --extra dev python -m pytest tests -q \
               && uv run --isolated --with-editable . --extra dev ruff check .

# reader-web(B2/B3 schema 再生、B4)
cd apps/reader-web && npm ci && npm test && npm run build

# API 形状变更再生(B2/B3)
cd apps/api && uv run --isolated --with-editable . --extra dev python -m app.export_openapi --out openapi.json
npx --yes openapi-typescript@7.13.0 apps/api/openapi.json -o apps/reader-web/src/lib/api/generated/schema.ts

# compose 校验(B1/B5)
cp .env.example .env
docker compose --profile worker --env-file .env -f infra/compose/docker-compose.base.yml config > /dev/null
docker compose --profile worker --env-file .env -f infra/compose/docker-compose.base.yml -f infra/compose/docker-compose.staging.yml config > /dev/null
docker compose --profile worker --env-file .env -f infra/compose/docker-compose.base.yml -f infra/compose/docker-compose.prod.yml config > /dev/null
docker compose --env-file .env -f infra/compose/docker-compose.edge.yml config > /dev/null

git diff --check
```

---

## 批次总览

| 批 | 名称 | 域 | 规模 | 一句话 | PR 标题建议 |
|---|---|---|---|---|---|
| B1 | worker LLM 日上限 | worker+infra | S | 交付 G 批硬门槛:评分日上限封顶失控花费 | `feat(worker): daily article cap for score_batch LLM scoring (G gate)` |
| B2 | 后端热路径 + CSRF fail-closed | api+worker | L | = 路线图 F 批(白名单已修正) | `perf+fix(api,worker): batch hot paths, real feed joins, CSRF fail-closed (F)` |
| B3 | admin users + benchmark 接线 | api+worker | M | = 路线图 E2 批(字段已修正) | `feat(api,worker): real admin users list + benchmark run wiring (E2)` |
| B4 | 前端竞态/超时/memo | reader-web | S-M | seq 守卫 + parseBlocks memo + 翻译超时 | `fix(reader-web): stale-response guards, memoized agent markdown, translate timeout` |
| B5 | 容器/运行时加固 | infra | M | healthcheck + 日志轮转 + 资源上限 + 非 root | `chore(infra): healthchecks, log rotation, resource limits, non-root images, worker heartbeat` |
| B6 | CI 缓存 + GHCR 保留 | .github | S-M | uv 缓存 + 镜像清理 + prod-current 锚 | `chore(ci): uv dependency cache, GHCR retention workflow, prod tag anchor` |
| B7 | 去重奇偶锁 + 测试补洞 | api+worker | S | 黄金表锁住双份实现;三个测试盲区 | `test+docs(api,worker): parity locks for duplicated LLM env parsing, behavior-gap tests` |

## 串行链与争用文件

```
B1 ──> B2 ──> B3 ──> B7        (后端道,严格串行)
 └───> B5                      (infra 道,B1 合并后)
B4、B6                          (随时并行,零争用)
```

| 争用文件 | 涉及批 | 处理 |
|---|---|---|
| `apps/worker/app/main.py` | B1(cap 接线)、B3(registry)、B7(注释) | 串行 B1→B3→B7 |
| `apps/api/app/api/routes/ask.py` | B2(`_active_score`)、B7(注释) | 串行 B2→B7 |
| `openapi.json` + `generated/schema.ts` | B2、B3(都再生) | **必冲突**,串行 B2→B3 |
| `infra/compose/docker-compose.base.yml` | B1(一行 env)、B5(重写服务块) | 串行 B1→B5 |
| `.env.example` | B1、B2 | 链内先后,无冲突 |
| reader-web | B2(仅 generated schema)、B4(组件 + client.ts) | 文件不相交 → B4 完全并行 |

**排序理由:先钱后安全。** 本轮两个真实风险是钱(worker LLM 无计量花费)和安全(CSRF fail-open)。B1 最小且封顶花费、解锁 G 门槛,最先;B2 紧随关 CSRF。B4/B6 零争用走并行道不占链;B7 收尾,因为它注释的文件全链都在动。每批 PR 合并即自动部署 staging,逐批实地验证。

---

## B1 — worker LLM 日上限(S)

**目标**:`score_batch` 处理前按 DB 计数强制日上限,封顶无人值守场景的 LLM 花费;这是 G 批(调度器)三个硬门槛中最后一个代码件。**只做上限机制,不做调度器。**

**白名单**:
- `apps/worker/app/jobs/score_batch.py`(cap 逻辑)
- `apps/worker/app/db/score_sink.py`(新增 `count_scores_today()`)
- `apps/worker/app/main.py`(`_score_batch` 读 env、传 cap)
- `apps/worker/tests/test_scoring.py`、`apps/worker/tests/test_score_sink.py`
- `infra/compose/docker-compose.base.yml`(worker env 一行:`SCHEDULE_SCORE_DAILY_ARTICLE_CAP: ${SCHEDULE_SCORE_DAILY_ARTICLE_CAP:-60}`)
- `.env.example`(`SCHEDULE_SCORE_DAILY_ARTICLE_CAP=60` + 注释)
- `infra/scripts/deploy.sh`(该变量加入行 32-40 的占位 unset 清单,与 `MINIMAX_*` 同款处理)

**要点**:
1. **env 名沿用 G 批约定 `SCHEDULE_SCORE_DAILY_ARTICLE_CAP`**,默认 60,`0` = 不限(镜像 `DailyCallBudget` 语义,budget.py:26-27)。本轮交付机制,G 后续只接调度入队器——同一旋钮,零改名。上限对**所有** `score_batch` 生效,不区分入队来源(今天唯一来源 = admin 路由 admin.py:132)。
2. `DatabaseScoreSink.count_scores_today()`:`SELECT COUNT(*) FROM article_base_scores WHERE scored_at >= :day_start`,`day_start` = UTC 当日零点的 **ISO 字符串**传参——Postgres(timestamptz 转换)与 `test_score_sink.py` 的 sqlite `:memory:` 引擎都兼容(sink 本就以 ISO 字符串写 `scored_at`,score_sink.py:183)。**error 行也计数** = 保守口径(失败行也代表一次真实 LLM 调用尝试),注释写明。
3. 截断语义:`score_batch()`(score_batch.py:19)进文章循环前取 `scored_today`,`remaining = max(cap - scored_today, 0)`;只对前 `remaining` 篇做 provider 调用 + `save_score`,其余**不评分不写行**(其 `scoring_batch_items` 保持 pending);**仍然** `finish_batch` + `enqueue_recommendations`(推荐基于已评部分照常生成)。结果载荷加 `"articles_skipped_cap": N, "daily_cap": cap, "scored_today_before": scored_today`;发生截断打一条 `LOGGER.warning`。
4. **失败语义:跳过 = 任务成功。绝不抛 `RetryableJobError`**——runner.py:75-82 会退避重排,过夜烧光重试次数形成重试风暴;也不 `mark_failed` 制造噪音。
5. **translate_article 不设 worker 侧上限**(定案,防 G 批再议):翻译只由用户触发,API 侧已有 `@limiter.limit(llm_rate_limit)`(articles.py:277-278,`5/minute;100/day`)+ 按文章 dedupe key + 已译缓存短路。
6. mock provider 同样计数(按行数计无法区分 provider;更简单,测试自注入 cap 值)。

**验收**:
- 单测三态:cap=0 → 全部评分;cap 部分余量 → 恰好 `remaining` 次 provider 调用(数 mock 调用次数),被跳过文章零 `article_base_scores` 行;cap 已耗尽 → 零 provider 调用、任务 `succeeded` 且 `articles_skipped_cap == len(articles)`。
- `count_scores_today` 只计今日(注入/冻结时钟)——sqlite 上过。
- compose config 渲染出该 env 默认 60;api+worker pytest、ruff、`git diff --check` 过。

---

## B2 — 后端热路径 + CSRF fail-closed(L,= 路线图 F 批)

**目标**:F 批六项原样执行,白名单与要点按 HEAD 实况修正(见 §前提修正 2/3/4)。

**白名单**:
- `apps/api/app/api/routes/recommendations.py`(改用新批量 `get_articles`)
- `apps/api/app/api/routes/ask.py`(`_active_score`,ask.py:196-204)
- `apps/api/app/api/routes/articles.py`(feed 真实字段;移除 `content_expired`;articles.py:96-100、113、135)
- `apps/api/app/db/repositories/articles.py`(新增 `get_articles(ids)`、article_sources/feeds join 加载器)
- `apps/api/app/db/repositories/scoring.py`、`recommendations.py`(仅当 join 助手落在这两处)
- `apps/api/app/core/security.py`(security.py:46-48 fail-open 翻转)
- `apps/api/app/main.py`(空 origins 启动大字告警)
- `apps/worker/app/db/recommendation_sink.py`(candidate 每 job 轮一算——实例级 memo,sink 生命周期 = 一个 job)
- `apps/worker/app/jobs/generate_recommendations.py`(`_load_online_ranking_module` 模块级缓存,:126-133;**保留**文件系统耦合本体,B7 注释标记)
- 再生:`apps/api/openapi.json`、`apps/reader-web/src/lib/api/generated/schema.ts`
- `.env.example`(一行注释:空 `AI_READER_CSRF_ALLOWED_ORIGINS` 现在会拒写)
- `CLAUDE.md`(37 行不变量措辞 → "feedHidden/feedQualityScore 预留——API 尚未下发这两个字段")
- 测试:`apps/api/tests/test_articles_api.py`、`test_ask.py`、新 `test_security.py`(或扩 `test_auth.py`)、`apps/worker/tests/test_recommendations.py`

**要点**:
1. **推荐 N+1(已缩窄)**:HEAD 的 recommendations.py:58-62 **已**批量加载 states/scores/feedbacks;唯剩 `recommendation_item_public` 内逐条 `get_article`(:29)。补 `article_repository.get_articles(ids)` 批量接口,循环改 dict 查找。目标:10 条推荐 ≤5 条查询。
2. `ask.py _active_score`:从"拉全部分数 Python 过滤"改为复用既有 `active_scores_for_articles([article.id])` 单查(或等价单行索引直查)。
3. 文章读路径 `feed.title`/`category`/`source_count` 硬编码占位 → 经 `article_sources` 真实 join;**`content_expired` 直接从响应移除**(已核实 reader-web 全库零引用),同 PR 再生 openapi/schema。
4. worker 推荐生成:候选集扫描"每用户一遍"→"每轮一算共享";ranking importlib 磁盘加载 → 模块级缓存(每进程一次)。耦合本体不动,注释标记"worker 跨 app 文件系统耦合——后续重构点"。
5. ⚠️ **CSRF fail-open → fail-closed**:`has_valid_csrf_origin()` 空 `allowed_origins` 时由放行改**拒绝非 GET**;`create_app()` 空配置时打大字 CRITICAL 告警。部署风险已降级(overlay 按 `${DOMAIN}` 硬编码注入 origins:staging.yml:25 / prod.yml:23),前提仅是 VPS `.env` 的 DOMAIN 正确 → OPS-2。
6. `feedHidden`/`feedQualityScore` 本轮不建后端列(维持路线图决策);只修 CLAUDE.md 措辞。

**验收**:
- CSRF:空 origins → 非 GET 403 + `caplog` 断言启动告警;GET 仍 200;合法 origin 放行。
- 查询计数断言(SQLAlchemy `event.listens_for(engine, "before_cursor_execute")` 计数器,用真 engine 的测试处):`/api/recommendations/latest` 10 条 ≤5 查询;`_active_score` = 1 查询。
- 列表+详情响应出真实 `feed.title`/`source_count`/`category`;schema 无 `content_expired`(再生已提交,`git diff --exit-code` 过)。
- smoke 三断言不回归;api+worker pytest、ruff、`npm run build`(schema 变更编译门)过。

---

## B3 — admin users + benchmark 接线(M,= 路线图 E2 批)

**目标**:E2 原样执行,users 字段按 schema 实况修正(**无 email 列**,见 §前提修正 5)。

**白名单**:
- `apps/api/app/api/routes/admin.py`(users 真查,admin.py:61-63 stub;`POST /api/admin/benchmarks` + `GET /api/admin/benchmarks/{id}`;拒 `model_swap` suite;非 mock provider 默认拒)
- `apps/api/app/db/auth_store.py`(list-users 查询)
- `apps/worker/app/db/benchmark_sink.py`(**新建**——写 `benchmark_runs`,表已存在于 0001_initial.py:405 **免迁移**;含 dry_run 成本预估路径)
- `apps/worker/app/main.py`(注册 `run_benchmark`,registry 6→7)
- 再生:`apps/api/openapi.json`、`apps/reader-web/src/lib/api/generated/schema.ts`
- 测试:`apps/api/tests/test_admin.py`、`apps/worker/tests/test_worker_registry.py`(EXPECTED_JOB_TYPES + `run_benchmark`)、新 `apps/worker/tests/test_benchmark_sink.py`

**要点**:
1. `GET /api/admin/users`:返回 `id / display_name / role / created_at / last_seen_at / is_demo`(`is_demo` = `display_name == "__demo__"`,auth_store.py:15)。**绝不**在载荷出现 `session_token_hash` / `recovery_code_hash`。
2. benchmark 接线:sink 落 `benchmark_runs`;`run_benchmark` 注册进 `build_handler_registry`(main.py:38-46 现为 6 个);`POST /api/admin/benchmarks` 建 run 行 + 入队(带 dedupe key)+ `GET .../{id}` 查状态。
3. 成本闸门:非 mock provider 一律拒,除非请求显式声明完整跑(`run_benchmark` 内已有 `BENCHMARK_MAX_PAIRS` / `BENCHMARK_MAX_COST_USD` 保持生效);`model_swap` suite handler 不支持 → API 层直接 4xx(最简)。

**验收**:demo/user 角色 → admin 端点 403(staging 边界不变量);admin → 200 且行含 `display_name` 无任何 hash;mock provider 下 `ci_mini` 端到端跑通写指标;非 mock 默认拒;`model_swap` → 4xx;registry 测试锁 7 个 job 类型;双侧 pytest、ruff、schema 再生门过。

---

## B4 — 前端竞态/超时/memo(S-M,随时并行)

**目标**:修 N9/N10/N11 三个已证实问题;与 B2 的唯一交集是 generated schema(文件不相交),完全并行安全。

**白名单**:
- `apps/reader-web/src/components/ReaderWorkbench.tsx` + `ReaderWorkbench.test.ts`
- `apps/reader-web/src/components/AgentMarkdown.tsx` + `AgentMarkdown.test.ts`
- `apps/reader-web/src/components/useArticleActions.ts` + `useArticleActions.test.ts`
- `apps/reader-web/src/lib/api/client.ts` + `client.test.ts`

**要点**:
1. **N9 seq 守卫**(ReaderWorkbench.tsx:129-195、291-298):`loadPage` 与 `loadRail` 各配独立 ref(`pageSeqRef`、`railSeqRef`),照抄 FocusedArticleScreen.tsx:34-64 的 requestSeqRef 模式——await 前取号,所有 set(含 `finally` 的 loading 位)先验号,过期即弃。守卫逻辑抽可导出纯函数/谓词供 node 测试(无 DOM)断言。**不动 FocusedArticleScreen**(精确编辑纪律)。
2. **N10 memo**(AgentMarkdown.tsx:171-172):`const blocks = useMemo(() => parseBlocks(text.trim()), [text]);` + 补 `useMemo` import。`parseBlocks` 保持模块私有。
3. **N11 翻译超时**(useArticleActions.ts:147-190):**复用** `linkedSignalWithTimeout`(client.ts:315,现为模块私有 → 加导出,零行为变更,client.test.ts 补直接测试:外部 abort / 超时 / cleanup 三态)。`translateFullText` 只包 `requestArticleTranslation` 的 POST(`TRANSLATE_REQUEST_TIMEOUT_MS = 30_000`),完成后 `cleanup()`;`timedOut()` 时给**明确错误文案**(不再静默 AbortError 返回),用户主动取消仍静默。**不包 `pollJobUntilTerminal`**——已有 60×1s 上限。不用 `AbortSignal.any/timeout`——库里已有测过的同用途助手。

**验收**:守卫单测(过期 seq → 响应被弃);AgentMarkdown parse 记忆化测试(同一 text 只 parse 一次,经抽出的计数器或引用相等断言);翻译超时 → 报错文案浮出、abort 仍静默;`linkedSignalWithTimeout` 导出测试三态;`npm test` + `npm run build` 绿。

---

## B5 — 容器/运行时加固(M,B1 合并后走 infra 道)

**目标**:修 N1/N2/N3-文档面。**先讲清 compose(非 swarm)healthcheck 的真实价值**:它不会自动重启不健康容器;价值 = `docker ps` 可见性 + `depends_on: condition` 门控 + smoke-test 断言。

**白名单**:
- `infra/compose/docker-compose.base.yml`(healthcheck、logging 锚、resources limits、depends_on condition)
- `infra/compose/docker-compose.edge.yml`(caddy 仅加 logging + 内存上限)
- `apps/api/Dockerfile`、`apps/worker/Dockerfile`、`apps/reader-web/Dockerfile`(非 root USER)
- 新建 `apps/api/.dockerignore`;新建**根 `.dockerignore`**(worker 构建上下文 = 仓库根,现在会上传 .git/.uv-cache/.worktrees/node_modules/output——白名单风格写)
- `apps/worker/app/runner.py` + `apps/worker/app/main.py`(心跳挂点)+ `apps/worker/tests/test_runner.py`
- `infra/scripts/smoke-test.sh`(`require_running` 增补:存在 `.State.Health` 时非 healthy 即失败)
- 新建 `docs/runbooks/backup-restore.md`(每日 cron + 异地副本章节,OPS-3 照此执行;写明现状:备份只在 prod 部署前跑、staging DB 无任何备份)

**要点(精确 compose 键)**:
1. **api**:`healthcheck: { test: ["CMD","python","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"], interval: 30s, timeout: 5s, retries: 3, start_period: 20s }`——`/healthz` 已存在(api main.py:63-69);stdlib urllib 跟随 smoke-test.sh:103-134 先例(零依赖,拒绝 httpx 探针的额外耦合)。
2. **worker(无 HTTP)= 心跳文件**:`run_forever` 加可选每轮回调,main.py 接 `Path(os.environ.get("WORKER_HEARTBEAT_FILE","/tmp/worker-heartbeat")).touch()`;healthcheck `["CMD","python","-c","import os,sys,time; p=os.environ.get('WORKER_HEARTBEAT_FILE','/tmp/worker-heartbeat'); sys.exit(0 if time.time()-os.path.getmtime(p)<960 else 1)"]`,`start_period: 30s`。**阈值 960s = 任务租约 900s + 余量**(一个长任务会阻塞轮询)。拒绝 `SELECT 1` DB 探活——测的是 postgres 不是轮询循环,且 DB 重启时把 worker 也标红。
3. **reader-web**:`["CMD","node","-e","fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]`(node:22 全局 fetch;容器内直连,不经 Authelia)。
4. **postgres**:`["CMD-SHELL","pg_isready -U postgres -d postgres"]`,interval 10s、retries 5(与 ci.yml:26 一致)。
5. **miniflux**:`["CMD","/usr/bin/miniflux","-healthcheck","auto"]`——⚠️ **staging 首部署核实**;fallback = 其 HTTP `/healthcheck` 端点(镜像不保证有 curl/wget)。**authelia** 自带内置 HEALTHCHECK,不动(staging `docker inspect` 核实)。**edge caddy** 跳过 healthcheck(deploy.sh 已 `caddy validate` + smoke 探公网 URL)。
6. **depends_on**:`miniflux.depends_on.postgres.condition: service_healthy`;`ai-reader-api.depends_on.postgres.condition: service_healthy`(新依赖,顺带提速 `wait_for_api_migration_ready`);`ai-reader-worker.depends_on: { postgres: {condition: service_healthy}, miniflux: {condition: service_started} }`——worker 靠任务重试容忍 miniflux 宕机,**不**耦合其健康。
7. **日志轮转**:文件顶部 `x-default-logging: &default-logging { driver: json-file, options: { max-size: "10m", max-file: "3" } }`,每服务 `logging: *default-logging`(base + edge 都加)。
8. **资源上限**:统一用 `deploy.resources.limits.{memory,cpus}`(Docker Compose v2 非 swarm 生效;假设写明——VPS 用 v2 插件,deploy.sh 的 `docker compose` 语法为证)。起步护栏(是上限不是调优):postgres 768M、worker 768M、api 512M、reader-web 512M、miniflux 384M、authelia 256M、caddy 256M。拒绝旧式 `mem_limit`——统一走 compose-spec 规范形。
9. **非 root**:python 两镜像 `useradd -m app` + `USER app`(app 目录属主对齐);reader-web 用 node:22-alpine 自带 `node` 用户。
10. ⚠️ **爆炸半径**:B5 合并后每环境首次 `up -d` 会因 config-hash 变化**重建全部容器含 postgres**(数据在卷上,安全;但 prod 要走 OPS-4:先手动备份 + 选静默窗口)。staging/prod 各有独立 postgres(`-p myrss-${ENV}`),半径按环境隔离。

**验收**:四 overlay config 校验过且渲染出 healthcheck/logging/resources;CI 镜像构建过;staging 部署后 `docker inspect --format '{{.State.Health.Status}}'` = healthy(api/worker/web/postgres/miniflux)且三 app 容器 `docker exec <c> id -u` ≠ 0;worker 心跳单测(回调推进 mtime);smoke-test 带新健康断言全过。**staging 部署本身即本批集成测试**;miniflux/authelia 探针若不符,按文中 fallback 处理并在 PR 记录。

---

## B6 — CI 缓存 + GHCR 保留(S-M,随时并行)

**目标**:修 N4。三件事:uv 依赖缓存、GHCR 镜像清理、防删现役 prod tag 的锚。

**白名单**:
- `.github/workflows/ci.yml`(uv 安装步替换 + 可选 Trivy 镜像扫描)
- 新建 `.github/workflows/ghcr-cleanup.yml`
- `.github/workflows/deploy-prod.yml`(`packages: write` + prod-current 重标步)

**要点**:
1. **uv 缓存最小 diff**:ci.yml:41-42 的 `python -m pip install -U uv` 替换为:
   ```yaml
   - name: Install uv
     uses: astral-sh/setup-uv@v5
     with:
       enable-cache: true
       cache-dependency-glob: |
         apps/api/pyproject.toml
         apps/worker/pyproject.toml
   ```
   保留 `actions/setup-python@v5`(uv 自动发现 3.12);所有 `uv run --isolated …` 调用不变。**无 uv.lock**(已核实)→ 只能 glob pyproject。拒绝手写 `actions/cache`——同效果、更多 YAML、无自动修剪。
2. **GHCR 清理**:`ghcr-cleanup.yml`,`schedule: cron "17 3 * * 1"` + `workflow_dispatch`(带 dry-run boolean),`permissions: { contents: read, packages: write }`,用 `dataaxiom/ghcr-cleanup-action@v1`——正确处理 multi-arch index 与 buildx attestation manifest(**天真 `gh api` 删版本会孤儿化/打断子 manifest**——build-push-action@v6 推 provenance manifest)。策略(三包 `ai-reader-web,ai-reader-api,ai-reader-worker` 各自):`delete-untagged: true`、`keep-n-tagged: 15`、`older-than: 30 days`、`exclude-tags: prod-current`、`validate: true`。**首跑必须 dry-run 手动**(OPS-5)。
3. **安全锚(关键)**:rollback.yml 接任意 `image_tag` 而仓库无处记录当前 prod 在用 tag → 若 prod >30 天未重部署,年龄策略可能删掉现役 tag。堵法:deploy-prod.yml 在 SSH 步之前加 GHCR 登录(`GITHUB_TOKEN`)+ 对三镜像 `docker buildx imagetools create -t ghcr.io/<owner>/<repo>/ai-reader-<x>:prod-current ghcr.io/…:${{ inputs.image_tag }}`(该 workflow 现仅 `contents: read`,需补 `packages: write`)。
4. **token 假设写明**:`GITHUB_TOKEN` 的 `packages: write` 足以删除本仓库 workflow 首发的包版本(仓库对包有 admin 角色)——dry-run 兼验此假设;fallback = classic PAT(`delete:packages`)入 secret。
5. 可选(做则做全):Trivy 镜像扫描 job(扫本地构建的三镜像,`ignore-unfixed: true`),排在镜像构建后。

**验收**:第二次 CI run 的 setup-uv 日志出现 cache restored;`ghcr-cleanup.yml` dry-run 列出的删除项**不含** `prod-current` 与最新 15 个 tag;下次 prod 部署后 GHCR UI 可见三镜像的 `prod-current` 标签。CI 本身即门。

---

## B7 — 去重奇偶锁 + 测试补洞(S,链尾收官)

**目标**:锁住 N5/N6 的双份实现(**定案:不去重,用测试锁**),补 N8 三个测试盲区。**非测试文件 diff 只许注释。**

**决策理由(写进代码注释)**:api 的 Docker 构建上下文仅 `apps/api`(ci.yml:291、compose base:59)——共享包要改两侧 Dockerfile + CI + compose 构建上下文,为 ~80 行助手不值(教学项目,最简足够);worker 运行时 import api 会扩大 F 批刻意只缓存不扩张的 importlib 文件系统耦合。**保留重复 + 双侧交叉引用注释 + 完全相同的黄金表奇偶测试**——任一侧漂移,其自己的测试套先红。

**白名单**:
- `apps/api/app/core/config.py`、`apps/worker/app/providers/llm.py`、`apps/api/app/api/routes/ask.py`、`apps/worker/app/main.py`(**仅注释/交叉引用**)
- `apps/worker/app/jobs/fetch_content.py`(:47-48 有意吞非 httpx 异常的意图注释)
- 新建 `apps/api/tests/test_llm_env_parity.py`、新建 `apps/worker/tests/test_llm_env_parity.py`(**两文件黄金表逐字相同**,本规格附表)
- `apps/worker/tests/test_fetch_content.py`(非 httpx 错 → fallback 不抛)
- `apps/api/tests/test_articles_api.py`(saved=false → project=false 级联,repo :293-294/:480-481)
- `apps/worker/tests/test_sinks_postgres.py`(并发 `enqueue_recommendations` 幂等,走 `ON CONFLICT … WHERE status IN ('queued','running')` 路径;`WORKER_QUEUE_POSTGRES_TEST_URL` 门控)

**黄金表覆盖**:`_parse_float` / `_parse_bool_with_default` / `_parse_optional_positive_int` / `_parse_optional_choice`(空串/空白/大小写/非法值抛 ValueError/0 与负数语义)+ `normalize_database_url`(api config.py:67-72 与 worker main.py:23-28 **也重复着**,一并锁)+ `_request_json` 载荷:worker 断言固定 config 的输出 dict;api 断言 = 同 dict + `"stream": True`。

**验收**:双侧 pytest、ruff 过;`git diff` 的非测试文件只有注释行;三个新行为测试红→绿各自可独立复现所述行为。

---

## 执行时决策汇总(已定死,执行时不再另选)

| # | 决策 | 定案 |
|---|---|---|
| D1 | worker 探活方式 | 心跳文件(阈值 960s=租约+余量);拒绝 DB 探活 |
| D2 | N5/N6 去重策略 | 不建共享包、不扩 importlib 耦合;重复+注释+黄金表奇偶锁(B7) |
| D3 | GHCR 清理机制 | dataaxiom/ghcr-cleanup-action@v1 + prod-current 浮动锚 + 首跑 dry-run |
| D4 | uv 缓存 | astral-sh/setup-uv@v5 enable-cache,key=两 pyproject glob |
| D5 | cap env 名与失败语义 | `SCHEDULE_SCORE_DAILY_ARTICLE_CAP`(G 契约名);跳过=成功,绝不 Retryable;translate 不设 worker 上限 |
| D6 | 翻译超时实现 | 导出并复用 `linkedSignalWithTimeout`(30s,只包 POST);不包 poll;不用 AbortSignal.timeout |
| D7 | 资源上限语法 | `deploy.resources.limits`(compose v2 非 swarm 生效,假设写明);拒绝 mem_limit |
| D8 | miniflux 探针 | `-healthcheck auto`,staging 首部署核实,fallback HTTP 端点 |

## 设计期前提修正(对路线图/走查原文的勘误)

1. **staging/prod 各有独立 postgres**(`docker compose -p myrss-${ENV}`;backup.sh:28 只备 prod)——B5 重建半径按环境隔离;staging DB 现状无任何备份(接受,runbook 写明)。
2. **F 第 1 条已部分完成**:states/scores/feedbacks 已批量(recommendations.py:58-62),唯剩 `get_article` 逐条 → F 缩为补 `get_articles(ids)`。
3. **API 形状变更触发 CI openapi/schema 回归门**(ci.yml:66)——F/E2 白名单原文漏了 `routes/articles.py`、`openapi.json`、`generated/schema.ts`,本文档已补。
4. **CSRF 部署风险降级**:overlay 已按 `${DOMAIN}` 注入 per-env origins(staging.yml:25 / prod.yml:23);smoke-test:222 登录带 Origin 自动验证边界。保留 OPS-2 核对,去掉"全断"表述。
5. **E2 字段修正**:`app_users` 无 email 列(models.py:31-49)→ 返回 `id/display_name/role/created_at/last_seen_at/is_demo`;绝不出 hash。
6. **B5 部署顺序坑**:deploy.sh 先 `up -d` 后备份 → OPS-4 前置手动备份。
7. worker 构建上下文 = 仓库根 → 根 `.dockerignore` 是真实构建提速,非美化。
8. `apps/scorer-worker/` 遗留残骸(compose/CI 零引用)——本轮不动,单列删除决策待用户拍板。
9. api/worker 无 uv.lock → 缓存 key 用 pyproject glob。
10. 本轮与 PR #13 文件重叠——#13 先合并,一切以 HEAD 为准。

## 扫描勘误(agent 误报,已核查推翻——防后续轮次复读)

1. ~~"B 批未合并"~~ → 在 main(`43289a7c` = PR #6),G 的 B 门槛已满足。
2. ~~"staging Miniflux 公开暴露 admin"~~ → Caddyfile:82 有 `forward_auth`,仅 /healthz 直通。
3. ~~".env 被 git 追踪"~~ → `git ls-files --error-unmatch .env` 确认未追踪。
4. ~~".env.example 缺 MiniMax 键"~~ → PR #13 已加全五键。
5. ~~"slowapi 缺 Request 参数"~~ → ask.py:155 有 `request: Request`。
6. ~~"推荐 N+1 是全新发现"~~ → 路线图 F 批第 1 条(KNOWN,且已部分完成,见前提修正 2)。
7. ~~"sessionCache in-flight 竞态"~~ → 单一共享 in-flight promise,两调用者拿同一结果,不成立。

## 本轮明确不做

- **G 批(调度器)**:三硬门槛中 B✓(main `43289a7`)、worker 预算→B1 交付;还差 **OPS-1(MiniMax 账户消费上限)**——运维完成后 G 才解锁,届时按路线图原 spec 单独走。
- `apps/scorer-worker/` 删除(待用户拍板的独立决策)。
- feedHidden/feedQualityScore 后端列(维持路线图决策:属新功能非接线)。
- 严格 CSP(安全 spec 原文:Next 内联运行时易误伤,先不加)。
- 列表虚拟化(12 条/页不需要)、AuthSessionGate 重构、骨架屏宽度微调(扫描中的弱发现,价值不足)。

## ⚠️ 运维清单(人工,带顺序约束;非 Codex 范围)

| # | 事项 | 必须先于 | 备注 |
|---|---|---|---|
| OPS-1 | MiniMax 控制台设**账户级消费上限** | 立即;G 解锁的最后门槛 | B1 之下的纵深防御 |
| OPS-2 | 核对 VPS `.env` 的 `DOMAIN` 正确(`docker compose … config \| grep CSRF` 确认渲染出的 origins = 真实公网域名) | **B2 的 prod 部署** | 部署后 smoke 登录自动验证 |
| OPS-3 | 每日备份 cron(如 `20 4 * * *` 跑 `backup.sh`)+ 异地副本(rclone/scp) | 最晚 G 之前;建议 B5 合并出 runbook 后即做 | 现状:备份只在 prod 部署前;staging DB 零备份 |
| OPS-4 | B5 上 prod 前:手动 `bash infra/scripts/backup.sh` + 选静默窗口 | **B5 的 prod 部署** | up -d 会重建 postgres 且先于部署内建备份步 |
| OPS-5 | `ghcr-cleanup.yml` 首跑 dry-run 人工核对(现役 prod tag + `prod-current` 不在删除列)后再启用 schedule | B6 定时清理生效前 | 兼验 GITHUB_TOKEN 删包权限假设 |

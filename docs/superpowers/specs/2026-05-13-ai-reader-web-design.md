# AI 阅读工作台前端设计

日期：2026-05-13
状态：设计已确认，可进入实施计划
适用阶段：第一版以单用户体验为主，保留未来多用户扩展边界

## 1. 背景与目标

当前系统已经具备 Miniflux RSS 抓取、Authelia 入口认证、PostgreSQL 存储、scorer-worker 周期评分与 digest 入库能力。Miniflux 适合作为稳定 RSS 后端和管理后台，但阅读页面、AI 分数展示、模块化排序和辅助阅读体验不足。

本设计新增一个独立的 AI 阅读工作台前端，作为日常主阅读入口。Miniflux 不改源码，继续负责 RSS 抓取、订阅源、分类、已读/未读、收藏和高级管理；新前端负责分数驱动的筛选、站内阅读、专注阅读、基础订阅源管理、当前文章 Agent 和稍后读等体验。

## 2. 设计结论

采用新增 `reader-web` 服务的方案：

```text
Browser
  -> Caddy + Authelia
  -> reader-web
      -> Miniflux API
      -> scoring PostgreSQL
      -> Minimax / LLM API
      -> Web search provider
```

`reader-web` 同时承载前端页面和后端 API。第一版电脑端优先，移动端只保证基础可用。Miniflux 保留为 RSS 引擎和高级后台，用户日常主要打开 AI 阅读工作台。

## 3. 组件职责

- **Miniflux**：负责订阅源、分类、文章抓取、已读/未读、收藏、原文链接、后台管理。
- **scorer-worker**：继续周期性拉取文章并评分；需要从单一总分升级为综合分 + 多维分。
- **reader-web**：负责文章模块、排序、阅读页面、基础订阅源管理、稍后读、当前文章 Agent。
- **scoring DB**：保存 AI 分数、标签、评分理由、digest，以及 Miniflux 没有的 reader 状态。
- **Authelia**：继续作为入口认证。第一版单用户优先，数据结构保留 `tenant_id` / `miniflux_user_id`。

## 4. 页面与阅读体验

第一版以电脑端三栏工作台为主：

```text
左侧：模块导航
中间：文章列表
右侧：阅读区 + 分数 + Agent
```

模块包括：未读、已读、收藏、稍后读、技术、商业、趋势、AI、产品、安全、订阅源管理。

文章列表显示标题、来源、发布时间、综合分、关键维度分、AI 标签和已读状态。模块内默认按对应维度排序，用户可以手动切换排序维度。已读文章不删除，只进入已读视图或弱化展示。

阅读区默认站内阅读，顶部提供来源、发布时间、打开原文按钮。标题下方展示综合分、7 个维度分、AI 标签和评分理由。阅读操作包括标记已读、收藏、稍后读。

专注阅读模式用于长文：隐藏模块栏和列表，正文居中、大字号、宽行距，只保留返回、收藏、稍后读、打开原文和 Agent 入口。

## 5. 多维评分设计

现有 `item_scores.score` 继续作为综合分，兼容已有 digest 逻辑。新增结构化多维分数字段，例如 `dimension_scores JSONB`，避免未来增加维度时频繁改表。

第一版维度：

- `importance`：重要性
- `usefulness`：实用性
- `timeliness`：时效性
- `depth`：深度
- `technical_value`：技术价值
- `business_value`：商业价值
- `trend_value`：趋势价值

LLM 评分输出形态：

```json
{
  "overall": 86,
  "importance": 90,
  "usefulness": 78,
  "timeliness": 84,
  "depth": 72,
  "technical_value": 92,
  "business_value": 48,
  "trend_value": 80,
  "tags": ["ai", "agent", "engineering"],
  "reason": "..."
}
```

模块默认排序：

- 未读：综合分
- 技术：技术价值
- 商业：商业价值
- 趋势：趋势价值 + 时效性
- AI：AI 标签 + 技术价值 / 趋势价值
- 产品：实用性 + 商业价值
- 安全：重要性 + 技术价值
- 已读：最近阅读时间
- 收藏：收藏时间或综合分
- 稍后读：加入时间或综合分

## 6. 订阅源管理与阅读状态

第一版新前端包含基础订阅源管理：

- 查看订阅源列表
- 查看订阅源所属分类
- 添加订阅源 URL
- 删除订阅源
- 手动刷新订阅源

复杂设置继续回 Miniflux，例如 crawler、rewrite rules、blocklist、认证 feed 和抓取错误排障。

阅读状态优先复用 Miniflux：

- 未读：Miniflux `unread`
- 已读：Miniflux `read`
- 收藏：Miniflux `starred`
- 稍后读：reader-web 自定义状态

新增 reader 状态表记录 Miniflux 没有的状态：

```text
reader_entry_states
  tenant_id
  miniflux_user_id
  miniflux_entry_id
  read_later
  last_read_at
  archived_at
  notes
```

`archived_at` 和 `notes` 为预留字段，第一版可以只实现 `read_later` 与 `last_read_at`。

## 7. 当前文章 Agent

Agent 第一版只做当前文章辅助阅读，不做全库 RAG。它必须支持流式传输，避免 LLM 响应慢时页面卡死。

Agent 输入上下文包括：

- 当前文章标题、正文、URL
- AI 评分理由、标签、维度分
- 用户在页面中选中的文字片段
- 必要时的联网搜索结果

交互方式：

- 快捷按钮：总结、5 个要点、解释术语、为什么值得读、和我的项目有什么关系、行动建议
- 自由追问：围绕当前文章继续提问
- 选中文字：正文选中一段后，可加入 Agent 输入框，或作为引用片段参与问答

Agent 使用 ReAct 风格的工具调用流程：先判断当前问题是否只需文章上下文，若涉及事实查证、最新版本、公司/产品/新闻、趋势判断，则调用联网搜索。界面不展示完整推理链，只展示资料来源、引用片段、搜索来源、结论、不确定点和行动建议。

联网策略：

- 总结、提炼要点、解释文章内部概念：默认不联网。
- 判断技术是否过时、版本是否最新、公司/产品近况、行业趋势：必须联网搜索。
- 搜索失败时允许基于当前文章回答，但必须明确提示“未完成联网查证”。

输出结构建议：

```text
结论
依据
引用
不确定点
行动建议
```

## 8. API 设计

第一版 `reader-web` API：

- `GET /api/modules`：模块列表和计数
- `GET /api/articles`：按模块、状态、排序维度、分页读取文章
- `GET /api/articles/:id`：读取文章正文、分数、标签、状态
- `POST /api/articles/:id/read`：标记已读
- `POST /api/articles/:id/star`：收藏或取消收藏
- `POST /api/articles/:id/read-later`：加入或移出稍后读
- `GET /api/feeds`：查看订阅源
- `POST /api/feeds`：添加订阅源
- `DELETE /api/feeds/:id`：删除订阅源
- `POST /api/feeds/:id/refresh`：手动刷新订阅源
- `POST /api/agent/article-chat`：当前文章 Agent，使用 streaming response 或 SSE 返回

## 9. 错误处理

- Miniflux 不可用：显示 RSS 后端暂不可用；不允许写已读、收藏和订阅源操作。
- scoring DB 不可用：文章仍可读，隐藏分数和 AI 排序，降级为发布时间排序。
- LLM 不可用：Agent 显示失败原因并允许重试；评分使用上次结果。
- 联网搜索失败：Agent 基于当前文章回答，但明确提示未完成联网查证。
- 文章正文为空或抓取差：提示建议打开原文。
- 流式响应中断：保留已输出内容，显示生成中断并提供重试。

## 10. 测试边界

第一版测试重点：

- 文章列表能按不同维度排序。
- 不同模块过滤正确。
- 已读、收藏能同步到 Miniflux。
- 稍后读能写入 reader 状态表。
- 多维评分 JSON 能解析，旧单分数数据能兼容。
- Agent 接口能流式返回。
- 选中文字能作为引用进入 Agent 请求。
- 联网搜索失败时 Agent 有明确降级提示。
- 单用户第一版可用，但数据写入不缺 `tenant_id` / `miniflux_user_id`。

## 11. 非目标

第一版不做这些：

- 完全替代 Miniflux 高级管理界面。
- 全库 RAG 或跨文章深度问答。
- 团队评论、共享推荐、多人协作工作流。
- 移动端精细体验。
- 修改 Miniflux 源码或 fork Miniflux 前端。

## 12. 后续实施顺序建议

1. 新增 `reader-web` 项目骨架、Dockerfile、Compose 接入和 Authelia/Caddy 路由。
2. 增加多维评分 schema 与 scorer-worker prompt/解析逻辑。
3. 实现文章列表 API 与模块排序。
4. 实现工作台页面、站内阅读和专注阅读。
5. 实现已读、收藏、稍后读状态写入。
6. 实现基础订阅源管理。
7. 实现当前文章 Agent 的流式问答、选中文字引用和联网搜索。
8. 补充测试、学习笔记与部署文档。

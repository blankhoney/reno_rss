"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  enqueueResearchJob,
  getInterestProfile,
  listClusters,
  listRules,
  listSavedSearches,
  listThemes,
  putRules,
  putSavedSearches,
  resetInterestProfile,
  researchCitationHref,
  savedSearchHref,
  searchAnnotations,
  type ClusterItem,
  type InterestProfile,
  type RuleItem,
  type SavedSearchItem,
  type ThemeItem,
} from "@/lib/api/intel";
import {
  cycleReaderMode,
  modeLabel,
  patchCraftPreferences,
  readCraftPreferences,
  type CraftPreferences,
} from "@/lib/craft/preferences";
import { getJob, listArticles, pollJobUntilTerminal, terminalJobStatus, type ApiJob } from "@/lib/api/articles";
import { AgentMarkdown } from "@/components/AgentMarkdown";
import type { Article } from "@/lib/articles/types";

function PanelShell({
  title,
  hint,
  children,
  actions,
}: {
  title: string;
  hint: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="productModulePane" aria-label={title}>
      <header className="articleListHeader">
        <div>
          <h1 className="articleListTitle">{title}</h1>
          <p className="workbenchRibbonMuted">{hint}</p>
        </div>
        {actions ? <div className="articleListActions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

export function ClustersPanel() {
  const [items, setItems] = useState<ClusterItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    let active = true;
    setError(null);
    listClusters(30)
      .then((next) => {
        if (active) setItems(next);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "加载故事线失败");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => reload(), [reload]);

  return (
    <PanelShell title="故事线 Clusters" hint="同一事件多源合并；主条 + 相关源。">
      {error ? (
        <p className="adminConsoleError" role="alert">
          {error}
          <button type="button" className="readerToolbarBtn" onClick={() => reload()}>
            重试
          </button>
        </p>
      ) : null}
      {items == null && !error ? <p className="workbenchRibbonMuted">加载中…</p> : null}
      {items && items.length === 0 ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">暂无故事线</p>
          <p className="articleListEmptyHint">有足够同日标题重叠文章后会自动聚类。</p>
        </div>
      ) : null}
      {items && items.length > 0 ? (
        <ul className="productModuleList">
          {items.map((item) => (
            <li key={item.id} className="productModuleCard">
              <Link href={`/read/${item.mainArticleId}?module=clusters&sort=default&lang=zh`} prefetch={false}>
                <strong>{item.label}</strong>
                <span className="workbenchRibbonMuted"> · {item.size} 源</span>
              </Link>
              {item.relatedArticleIds.length > 0 ? (
                <p className="workbenchRibbonMuted">
                  相关：
                  {item.relatedArticleIds.slice(0, 5).map((id) => (
                    <Link key={id} href={`/read/${id}?module=clusters&sort=default&lang=zh`} prefetch={false}>
                      {" "}
                      #{id}
                    </Link>
                  ))}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </PanelShell>
  );
}

export function ThemesPanel() {
  const [items, setItems] = useState<ThemeItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<CraftPreferences>(() => readCraftPreferences());

  const reload = useCallback(() => {
    let active = true;
    setError(null);
    listThemes(40)
      .then((next) => {
        if (active) setItems(next);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "加载主题失败");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => reload(), [reload]);

  function togglePin(label: string) {
    const pinned = new Set(prefs.pinnedThemes);
    if (pinned.has(label)) pinned.delete(label);
    else pinned.add(label);
    setPrefs(patchCraftPreferences({ pinnedThemes: [...pinned] }));
  }

  return (
    <PanelShell title="主题簇 Themes" hint="来自评分标签；可钉选后从精读跳转相关源。">
      {error ? (
        <p className="adminConsoleError" role="alert">
          {error}
          <button type="button" className="readerToolbarBtn" onClick={() => reload()}>
            重试
          </button>
        </p>
      ) : null}
      {prefs.pinnedThemes.length > 0 ? (
        <p className="workbenchRibbonMuted">已钉选：{prefs.pinnedThemes.join(" · ")}</p>
      ) : null}
      {items == null && !error ? <p className="workbenchRibbonMuted">加载中…</p> : null}
      {items && items.length > 0 ? (
        <ul className="productModuleList">
          {items.map((item) => {
            const pinned = prefs.pinnedThemes.includes(item.label);
            return (
              <li key={item.label} className="productModuleCard">
                <div className="productModuleRow">
                  <div>
                    <strong>{item.label}</strong>
                    <span className="workbenchRibbonMuted"> · weight {item.weight.toFixed(1)}</span>
                    <p className="workbenchRibbonMuted">
                      {item.articleIds.slice(0, 4).map((id) => (
                        <Link key={id} href={`/read/${id}?module=themes&sort=default&lang=zh`} prefetch={false}>
                          #{id}{" "}
                        </Link>
                      ))}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="readerToolbarBtn"
                    onClick={() => togglePin(item.label)}
                  >
                    {pinned ? "取消钉选" : "钉选"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
      {items != null && items.length === 0 ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">尚无主题簇</p>
          <p className="articleListEmptyHint">评分生成标签后会显示主题热度。</p>
        </div>
      ) : null}
    </PanelShell>
  );
}

export function RulesPanel() {
  const [rules, setRules] = useState<RuleItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftType, setDraftType] = useState("mute");
  const [draftKeyword, setDraftKeyword] = useState("");
  const [draftFeedId, setDraftFeedId] = useState("");
  const [draftWeight, setDraftWeight] = useState("10");
  const [saving, setSaving] = useState(false);

  const reload = useCallback(() => {
    listRules()
      .then(setRules)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "加载规则失败"));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function addRule() {
    if (rules == null) return;
    setSaving(true);
    setError(null);
    try {
      const next: RuleItem = {
        type: draftType,
        keyword: draftKeyword.trim() || null,
        feedId: draftFeedId.trim() ? Number(draftFeedId) : null,
        weight:
          draftType === "boost" || draftType === "keyword" || draftType === "score_threshold"
            ? Number(draftWeight) || 10
            : null,
      };
      const saved = await putRules([...rules, next]);
      setRules(saved);
      setDraftKeyword("");
      setDraftFeedId("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存规则失败");
    } finally {
      setSaving(false);
    }
  }

  async function removeRule(index: number) {
    if (rules == null) return;
    setSaving(true);
    setError(null);
    try {
      const next = rules.filter((_, i) => i !== index);
      setRules(await putRules(next));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除规则失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <PanelShell
      title="规则引擎"
      hint="boost / mute / must_read / keyword / score_threshold —— 写入后参与 Top10 与简报排序。"
    >
      {error ? <p className="adminConsoleError" role="alert">{error}<button type="button" className="readerToolbarBtn" onClick={reload}>重试</button></p> : null}
      {rules == null && !error ? <p className="workbenchRibbonMuted">加载中…</p> : null}
      {rules != null && rules.length === 0 ? <p className="workbenchRibbonMuted">尚无规则。</p> : null}
      <div className="productModuleForm">
        <label>
          类型
          <select value={draftType} onChange={(event) => setDraftType(event.target.value)}>
            <option value="mute">mute</option>
            <option value="boost">boost</option>
            <option value="must_read">must_read</option>
            <option value="keyword">keyword</option>
            <option value="score_threshold">score_threshold</option>
          </select>
        </label>
        <label>
          feed_id
          <input value={draftFeedId} onChange={(event) => setDraftFeedId(event.target.value)} placeholder="可选" />
        </label>
        <label>
          keyword
          <input value={draftKeyword} onChange={(event) => setDraftKeyword(event.target.value)} placeholder="可选" />
        </label>
        <label>
          weight
          <input value={draftWeight} onChange={(event) => setDraftWeight(event.target.value)} />
        </label>
        <button type="button" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={saving || rules == null} onClick={addRule}>
          添加规则
        </button>
      </div>
      <ul className="productModuleList">
        {(rules ?? []).map((rule, index) => (
          <li key={`${rule.type}-${index}`} className="productModuleCard productModuleRow">
            <code>
              {rule.type}
              {rule.feedId != null ? ` feed=${rule.feedId}` : ""}
              {rule.keyword ? ` kw=${rule.keyword}` : ""}
              {rule.weight != null ? ` w=${rule.weight}` : ""}
            </code>
            <button type="button" className="readerToolbarBtn" disabled={saving} onClick={() => removeRule(index)}>
              删除
            </button>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}

export function SavedSearchesPanel() {
  const [items, setItems] = useState<SavedSearchItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [q, setQ] = useState("");
  const [filterModule, setFilterModule] = useState("all");
  const [sort, setSort] = useState("latest");

  const reload = useCallback(() => {
    setError(null);
    listSavedSearches()
      .then(setItems)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "加载失败"));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function saveCurrent() {
    if (!name.trim() || items == null) return;
    try {
      const next = await putSavedSearches([
        ...items,
        { name: name.trim(), q: q.trim(), module: filterModule, sort },
      ]);
      setItems(next);
      setName("");
      setQ("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败");
    }
  }

  return (
    <PanelShell title="保存的搜索" hint="过滤器可复用；点击跳回列表。">
      {error ? <p className="adminConsoleError" role="alert">{error}<button type="button" className="readerToolbarBtn" onClick={reload}>重试</button></p> : null}
      {items == null && !error ? <p className="workbenchRibbonMuted">加载中…</p> : null}
      {items != null && items.length === 0 ? <p className="workbenchRibbonMuted">尚无保存的搜索。</p> : null}
      <div className="productModuleForm">
        <label>
          名称
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          查询
          <input value={q} onChange={(event) => setQ(event.target.value)} />
        </label>
        <label>
          文章过滤
          <select value={filterModule} onChange={(event) => setFilterModule(event.target.value)}>
            <option value="all">全部</option>
            <option value="unread">未读</option>
            <option value="read">已读</option>
            <option value="read-later">稍后读</option>
            <option value="starred">候选</option>
            <option value="project">立项</option>
          </select>
        </label>
        <label>
          排序
          <select value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="latest">最新</option>
            <option value="score">总分</option>
            <option value="technical">技术</option>
            <option value="business">商业</option>
            <option value="trend">趋势</option>
          </select>
        </label>
        <button type="button" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={items == null} onClick={saveCurrent}>
          保存
        </button>
      </div>
      <ul className="productModuleList">
        {(items ?? []).map((item) => (
          <li key={`${item.name}-${item.q}`} className="productModuleCard">
            <Link
              href={savedSearchHref(item)}
              prefetch={false}
            >
              <strong>{item.name}</strong>
              <span className="workbenchRibbonMuted">
                {" "}
                · {item.module}
                {item.q ? ` · ${item.q}` : ""}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}

const RESEARCH_TEMPLATES: Array<{
  id: string;
  label: string;
  scope: "topn" | "project" | "topic";
  question: string;
  topic?: string;
}> = [
  {
    id: "weekly",
    label: "周研究简报",
    scope: "topn",
    question: "请生成本周研究简报：关键信号、风险、值得立项项，分条列出并引用原文。",
  },
  {
    id: "radar",
    label: "技术/竞品雷达",
    scope: "topic",
    topic: "radar",
    question: "请做技术与竞品雷达：新动向、分化、空白机会，按优先级排序并给引用。",
  },
  {
    id: "onepager",
    label: "立项一页纸",
    scope: "project",
    question: "请把当前立项队列整理成一页纸：问题、洞察、下一步行动、风险。",
  },
];

type ResearchResult = {
  answer?: string;
  citations?: Array<{
    article_id?: number;
    title?: string;
    quote?: string;
    start_hint?: number;
  }>;
  provider?: string;
  question?: string;
};

export function researchResultFromJob(job: ApiJob, fallbackQuestion: string): ResearchResult {
  const raw = (job.result ?? {}) as Record<string, unknown>;
  const brief = raw.brief && typeof raw.brief === "object" ? (raw.brief as Record<string, unknown>) : raw;
  return {
    answer: typeof brief.answer === "string" ? brief.answer : undefined,
    citations: Array.isArray(brief.citations)
      ? (brief.citations as Array<{
          article_id?: number;
          title?: string;
          quote?: string;
          start_hint?: number;
        }>)
      : [],
    provider: typeof brief.provider === "string" ? brief.provider : undefined,
    question: typeof brief.question === "string" ? brief.question : fallbackQuestion,
  };
}

export function parseResearchJobId(raw: string | null | undefined): number | null {
  if (raw == null || !/^\d+$/.test(raw)) return null;
  const jobId = Number(raw);
  return Number.isSafeInteger(jobId) && jobId > 0 ? jobId : null;
}

export function ResearchPanel({ initialJobId = null }: { initialJobId?: number | null }) {
  const router = useRouter();
  const [scope, setScope] = useState<"topn" | "project" | "topic">("topn");
  const [topic, setTopic] = useState("");
  const [question, setQuestion] = useState("总结本周最值得跟进的信号与风险");
  const [jobId, setJobId] = useState<number | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const activeJobRef = useRef<number | null>(null);
  const pollAbortRef = useRef<AbortController | null>(null);
  const questionRef = useRef(question);

  useEffect(() => {
    questionRef.current = question;
  }, [question]);

  const researchHref = useCallback((nextJobId: number) => {
    const params = new URLSearchParams({ module: "research", sort: "default", lang: "zh", job: String(nextJobId) });
    return `?${params.toString()}`;
  }, []);

  const resumeJob = useCallback(async (nextJobId: number) => {
    if (activeJobRef.current === nextJobId) return;
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;
    activeJobRef.current = nextJobId;
    setBusy(true);
    setError(null);
    setResult(null);
    setJobId(nextJobId);
    try {
      const initial = await getJob(nextJobId, { signal: controller.signal });
      if (controller.signal.aborted || activeJobRef.current !== nextJobId) return;
      setStatus(initial.status);
      const terminal = terminalJobStatus(initial.status)
        ? initial
        : await pollJobUntilTerminal(nextJobId, { signal: controller.signal });
      if (controller.signal.aborted || activeJobRef.current !== nextJobId) return;
      setStatus(terminal.status);
      if (terminal.status === "failed") {
        throw new Error(terminal.lastError || "研究任务失败，可重试");
      }
      if (terminal.status !== "succeeded") {
        throw new Error("研究任务仍在运行，请稍后再次打开或重试轮询");
      }
      setResult(researchResultFromJob(terminal, questionRef.current));
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(caught instanceof Error ? caught.message : "研究任务失败");
    } finally {
      if (activeJobRef.current === nextJobId) {
        setBusy(false);
        activeJobRef.current = null;
      }
    }
  }, []);

  useEffect(() => {
    if (initialJobId == null) return;
    void resumeJob(initialJobId);
    return () => {
      pollAbortRef.current?.abort();
    };
  }, [initialJobId, resumeJob]);

  useEffect(() => {
    return () => {
      pollAbortRef.current?.abort();
    };
  }, []);

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const job = await enqueueResearchJob({
        scope,
        question,
        topic: scope === "topic" ? topic : undefined,
      });
      setJobId(job.jobId);
      setStatus("queued");
      router.push(researchHref(job.jobId));
      void resumeJob(job.jobId);
    } catch (caught) {
      setBusy(false);
      setError(caught instanceof Error ? caught.message : "研究任务失败");
    }
  }

  function exportMarkdown() {
    if (!result?.answer) return;
    const lines = [
      `# 研究简报`,
      "",
      `问题：${result.question || question}`,
      `provider：${result.provider || "unknown"}`,
      "",
      result.answer,
      "",
      "## 引用",
      ...(result.citations ?? []).map(
        (item, index) =>
          `${index + 1}. [#${item.article_id ?? "?"}] ${item.title ?? ""} — ${item.quote ?? ""}`,
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "research-brief.md";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <PanelShell title="语料研究 Agent" hint="跨 TopN / 项目 / 主题提问；异步 job，可轮询导出。">
      {error ? <p className="adminConsoleError">{error}</p> : null}
      <div className="articleListActions">
        {RESEARCH_TEMPLATES.map((template) => (
          <button
            key={template.id}
            type="button"
            className="readerToolbarBtn"
            onClick={() => {
              setScope(template.scope);
              setTopic(template.topic ?? "");
              setQuestion(template.question);
            }}
          >
            {template.label}
          </button>
        ))}
      </div>
      <div className="productModuleForm">
        <label>
          范围
          <select value={scope} onChange={(event) => setScope(event.target.value as typeof scope)}>
            <option value="topn">今日 TopN</option>
            <option value="project">立项队列</option>
            <option value="topic">主题</option>
          </select>
        </label>
        {scope === "topic" ? (
          <label>
            主题
            <input value={topic} onChange={(event) => setTopic(event.target.value)} />
          </label>
        ) : null}
        <label>
          问题
          <input value={question} onChange={(event) => setQuestion(event.target.value)} />
        </label>
        <button type="button" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={busy} onClick={run}>
          {busy ? "运行中…" : "启动研究"}
        </button>
      </div>
      {jobId != null ? (
        <p className="workbenchRibbonMuted">
          job #{jobId} · {status}
          {result?.provider ? ` · ${result.provider}` : ""}
        </p>
      ) : null}
      {result?.answer ? (
        <section className="productModuleCard" aria-label="研究回答">
          <div className="articleListActions">
            <button type="button" className="readerToolbarBtn" onClick={exportMarkdown}>
              导出 Markdown
            </button>
          </div>
          <AgentMarkdown text={result.answer} />
          {(result.citations?.length ?? 0) > 0 ? (
            <ul className="productModuleList">
              {result.citations!.map((item, index) => (
                <li key={`${item.article_id}-${index}`} className="productModuleCard">
                  {item.article_id != null ? (
                    <Link
                      href={researchCitationHref(item.article_id, item.quote, jobId ?? undefined)}
                      prefetch={false}
                    >
                      [{index + 1}] {item.title || `文章 #${item.article_id}`}
                    </Link>
                  ) : (
                    <strong>
                      [{index + 1}] {item.title || "引用"}
                    </strong>
                  )}
                  <p className="workbenchRibbonMuted">{item.quote}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </PanelShell>
  );
}

export function InterestPanel() {
  const [profile, setProfile] = useState<InterestProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isResetting, setIsResetting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    getInterestProfile()
      .then(setProfile)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "加载兴趣向量失败"));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function onReset() {
    setIsResetting(true);
    setError(null);
    setMessage(null);
    try {
      setProfile(await resetInterestProfile());
      setMessage("兴趣向量已重置");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重置失败");
    } finally {
      setIsResetting(false);
    }
  }

  function onExport() {
    if (!profile) return;
    const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "ai-reader-interest.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <PanelShell
      title="兴趣向量"
      hint="来自反馈、划线、立项的长期偏好；可重置、可导出。"
      actions={
        <>
          <button type="button" className="readerToolbarBtn" onClick={onExport} disabled={profile == null || isResetting}>
            导出 JSON
          </button>
          <button type="button" className="readerToolbarBtn" onClick={onReset} disabled={isResetting}>
            {isResetting ? "重置中…" : "重置"}
          </button>
        </>
      }
    >
      {error ? <p className="adminConsoleError" role="alert">{error}<button type="button" className="readerToolbarBtn" onClick={reload}>重试</button></p> : null}
      {message ? <p className="adminConsoleMessage">{message}</p> : null}
      {profile == null && !error ? <p className="workbenchRibbonMuted">加载中…</p> : null}
      {profile ? (
        <>
          <p className="workbenchRibbonMuted">
            立项 {profile.projectCount} · 划线 {profile.annotationCount}
            {profile.resetAt ? ` · 重置于 ${profile.resetAt.slice(0, 16)}` : ""}
          </p>
          <ul className="productModuleList">
            {profile.keywords.map((item) => (
              <li key={item.term} className="productModuleCard">
                {item.term}
                <span className="workbenchRibbonMuted"> · {item.weight.toFixed(2)}</span>
              </li>
            ))}
          </ul>
          {profile.keywords.length === 0 ? (
            <p className="workbenchRibbonMuted">尚无足够信号；多反馈与划线后会形成向量。</p>
          ) : null}
        </>
      ) : null}
    </PanelShell>
  );
}

export function UnifiedSearchPanel({
  initialQuery = "",
  initialArticleModule = "all",
  initialSort = "default",
}: {
  initialQuery?: string;
  initialArticleModule?: string;
  initialSort?: string;
}) {
  const router = useRouter();
  const [q, setQ] = useState(initialQuery);
  const [articleModule, setArticleModule] = useState(initialArticleModule);
  const [articleSort, setArticleSort] = useState(initialSort);
  const [articles, setArticles] = useState<Article[]>([]);
  const [annotations, setAnnotations] = useState<
    Array<{
      id: number;
      articleId: number;
      content: string;
      selectedText: string | null;
      articleTitle: string | null;
    }>
  >([]);
  const [error, setError] = useState<string | null>(null);
  const [articleError, setArticleError] = useState<string | null>(null);
  const [annotationError, setAnnotationError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const searchSeqRef = useRef(0);
  const lastSearchKeyRef = useRef<string | null>(null);

  const searchHref = useCallback((query: string, module: string, sort: string) => {
    const params = new URLSearchParams({ module: "search", filter: module, sort, lang: "zh" });
    const normalized = query.trim();
    if (normalized) params.set("q", normalized);
    return `?${params.toString()}`;
  }, []);

  const runSearch = useCallback(async (query: string, module: string, sort: string) => {
    const normalized = query.trim();
    if (!normalized) {
      searchSeqRef.current += 1;
      lastSearchKeyRef.current = null;
      setError("请输入标题、正文、划线或笔记关键词");
      setArticleError(null);
      setAnnotationError(null);
      return;
    }

    const searchKey = `${normalized} ${module} ${sort}`;
    const requestSeq = searchSeqRef.current + 1;
    searchSeqRef.current = requestSeq;
    lastSearchKeyRef.current = searchKey;
    const isCurrent = () => requestSeq === searchSeqRef.current;
    setBusy(true);
    setError(null);
    setArticleError(null);
    setAnnotationError(null);
    setArticles([]);
    setAnnotations([]);

    const [articleResult, annotationResult] = await Promise.allSettled([
      listArticles({ limit: 50, module, q: normalized, sort }),
      searchAnnotations(normalized),
    ]);
    if (!isCurrent()) return;

    if (articleResult.status === "fulfilled") {
      setArticles(articleResult.value.articles);
    } else {
      setArticleError(articleResult.reason instanceof Error ? articleResult.reason.message : "文章搜索失败");
    }
    if (annotationResult.status === "fulfilled") {
      setAnnotations(annotationResult.value);
    } else {
      setAnnotationError(
        annotationResult.reason instanceof Error ? annotationResult.reason.message : "划线/笔记搜索失败",
      );
    }
    setSearched(true);
    setBusy(false);
  }, []);

  useEffect(() => {
    setQ(initialQuery);
    setArticleModule(initialArticleModule);
    setArticleSort(initialSort);
    const normalized = initialQuery.trim();
    if (!normalized) {
      searchSeqRef.current += 1;
      lastSearchKeyRef.current = null;
      setArticles([]);
      setAnnotations([]);
      setArticleError(null);
      setAnnotationError(null);
      setSearched(false);
      setBusy(false);
      return;
    }
    const searchKey = `${normalized} ${initialArticleModule} ${initialSort}`;
    if (lastSearchKeyRef.current !== searchKey) {
      void runSearch(initialQuery, initialArticleModule, initialSort);
    }
  }, [initialArticleModule, initialQuery, initialSort, runSearch]);

  function submitSearch() {
    const normalized = q.trim();
    if (!normalized) {
      void runSearch(q, articleModule, articleSort);
      return;
    }
    const href = searchHref(normalized, articleModule, articleSort);
    if (window.location.search === href) {
      void runSearch(normalized, articleModule, articleSort);
      return;
    }
    router.push(href);
  }

  function readerHref(articleId: number) {
    const params = new URLSearchParams({
      module: "search",
      filter: articleModule,
      sort: articleSort,
      lang: "zh",
      q: q.trim(),
    });
    return `/read/${articleId}?${params.toString()}`;
  }

  return (
    <PanelShell title="统一搜索" hint="一次检索标题、正文、私人划线与笔记；中英文子串均可命中。">
      {error ? <p className="adminConsoleError">{error}</p> : null}
      <div className="productModuleForm">
        <label>
          关键词
          <input value={q} onChange={(event) => setQ(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter") submitSearch();
          }} />
        </label>
        <label>
          文章过滤
          <select value={articleModule} onChange={(event) => setArticleModule(event.target.value)}>
            <option value="all">全部</option>
            <option value="unread">未读</option>
            <option value="read">已读</option>
            <option value="read-later">稍后读</option>
            <option value="starred">候选</option>
            <option value="project">立项</option>
          </select>
        </label>
        <label>
          文章排序
          <select value={articleSort} onChange={(event) => setArticleSort(event.target.value)}>
            <option value="default">默认</option>
            <option value="latest">最新</option>
            <option value="score">总分</option>
            <option value="technical">技术</option>
            <option value="business">商业</option>
            <option value="trend">趋势</option>
          </select>
        </label>
        <button type="button" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={busy} onClick={submitSearch}>
          {busy ? "搜索中…" : "搜索"}
        </button>
      </div>
      {searched ? (
        <p className="workbenchRibbonMuted">文章 {articles.length} · 划线/笔记 {annotations.length}</p>
      ) : null}
      {articleError ? <p className="adminConsoleError" role="alert">文章搜索失败：{articleError}</p> : null}
      {annotationError ? <p className="adminConsoleError" role="alert">划线/笔记搜索失败：{annotationError}</p> : null}
      {searched && articles.length === 0 && annotations.length === 0 && !articleError && !annotationError ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">没有匹配结果</p>
          <p className="articleListEmptyHint">尝试缩短关键词，或先同步正文再搜索。</p>
        </div>
      ) : null}
      {articles.length > 0 ? <h2 className="productModuleSectionTitle">文章标题 / 正文</h2> : null}
      <ul className="productModuleList">
        {articles.map((article) => (
          <li key={article.id} className="productModuleCard">
            <Link href={readerHref(article.id)} prefetch={false}>
              <strong>{article.title}</strong>
            </Link>
            <p className="workbenchRibbonMuted">
              {article.feedTitle}{article.summaryZh ? ` · ${article.summaryZh}` : ""}
            </p>
          </li>
        ))}
      </ul>
      {annotations.length > 0 ? <h2 className="productModuleSectionTitle">私人划线 / 笔记</h2> : null}
      <ul className="productModuleList">
        {annotations.map((item) => (
          <li key={item.id} className="productModuleCard">
            <Link href={readerHref(item.articleId)} prefetch={false}>
              <strong>{item.articleTitle || `文章 #${item.articleId}`}</strong>
            </Link>
            <p>{item.selectedText || item.content}</p>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}

/** Backward-compatible route for old ?module=notes bookmarks. */
export function NotesSearchPanel() {
  return <UnifiedSearchPanel />;
}

export function CraftPanel() {
  const [prefs, setPrefs] = useState<CraftPreferences>(() => readCraftPreferences());

  function update(patch: Partial<CraftPreferences>) {
    setPrefs(patchCraftPreferences(patch));
  }

  return (
    <PanelShell title="阅读工艺" hint="Scan / Focus / Keep 三态 + 密度 + 双栏，状态本地持久。">
      <div className="productModuleForm">
        <label>
          当前态
          <button
            type="button"
            className="readerToolbarBtn readerToolbarBtnPrimary"
            onClick={() => update({ mode: cycleReaderMode(prefs.mode) })}
          >
            {modeLabel(prefs.mode)}
          </button>
        </label>
        <label>
          密度
          <select
            value={prefs.density}
            onChange={(event) =>
              update({ density: event.target.value === "compact" ? "compact" : "comfortable" })
            }
          >
            <option value="comfortable">舒适</option>
            <option value="compact">紧凑</option>
          </select>
        </label>
        <label>
          双栏
          <input
            type="checkbox"
            checked={prefs.dualPane}
            onChange={(event) => update({ dualPane: event.target.checked })}
          />
        </label>
        <label>
          双栏内容
          <select
            value={prefs.dualPaneKind}
            onChange={(event) =>
              update({ dualPaneKind: event.target.value === "article" ? "article" : "notes" })
            }
          >
            <option value="notes">文章 + 笔记</option>
            <option value="article">两篇文章对照</option>
          </select>
        </label>
        <label>
          对照文章 ID
          <input
            value={prefs.dualArticleId ?? ""}
            onChange={(event) => {
              const raw = event.target.value.trim();
              const id = Number(raw);
              update({
                dualArticleId: raw && Number.isFinite(id) && id > 0 ? Math.floor(id) : null,
              });
            }}
            placeholder="例如 42"
          />
        </label>
      </div>
      <p className="workbenchRibbonMuted">
        模式会写入 localStorage，并在 documentElement 上暴露 data-reader-mode / data-density /
        data-dual-pane，供列表与精读页读取。双文对照在精读页右侧加载第二篇。
      </p>
    </PanelShell>
  );
}

export function ExportPanel() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingFormat, setPendingFormat] = useState<"markdown" | "json" | "zip" | null>(null);

  async function download(format: "markdown" | "json" | "zip") {
    if (pendingFormat != null) return;
    setPendingFormat(format);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`/api/export/project?format=${format}`, {
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`导出失败 (${response.status})`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        format === "markdown"
          ? "project-export.md"
          : format === "json"
            ? "project-export.json"
            : "project-export.zip";
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage(`已下载 ${format}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导出失败");
    } finally {
      setPendingFormat(null);
    }
  }

  return (
    <PanelShell title="立项导出" hint="Markdown / JSON / zip 包，不绑死笔记软件。">
      {error ? <p className="adminConsoleError">{error}</p> : null}
      {message ? <p className="workbenchRibbonMuted">{message}</p> : null}
      <div className="articleListActions">
        <button type="button" className="readerToolbarBtn" disabled={pendingFormat != null} onClick={() => void download("markdown")}>
          {pendingFormat === "markdown" ? "导出中…" : "Markdown"}
        </button>
        <button type="button" className="readerToolbarBtn" disabled={pendingFormat != null} onClick={() => void download("json")}>
          {pendingFormat === "json" ? "导出中…" : "JSON"}
        </button>
        <button type="button" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={pendingFormat != null} onClick={() => void download("zip")}>
          {pendingFormat === "zip" ? "导出中…" : "ZIP"}
        </button>
      </div>
    </PanelShell>
  );
}

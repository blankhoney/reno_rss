/** Dispatched by command palette to focus the workbench article list for j/k. */
export const FOCUS_ARTICLE_LIST_EVENT = "ai-reader:focus-article-list";

export type CommandKind = "navigate" | "action";

export type CommandItem = {
  id: string;
  label: string;
  keywords: string[];
  kind: CommandKind;
  /** Navigation target when kind === "navigate" */
  href?: string;
  /** Action id when kind === "action" */
  action?:
    | "toggle-theme"
    | "focus-list"
    | "cycle-mode"
    | "toggle-density"
    | "toggle-dual-pane"
    | "admin-sync"
    | "admin-brief"
    | "admin-govern"
    | "open-usage";
  group: string;
  shortcut?: string;
};

export function moduleHref(
  moduleId: string,
  sort: string = "default",
  lang: string = "zh",
  q?: string,
): string {
  const qs = new URLSearchParams({ module: moduleId, sort, lang });
  if (q && q.trim()) qs.set("q", q.trim());
  return `/?${qs.toString()}`;
}

/** When the user types free text, search articles and private annotations together. */
export function searchArticlesCommand(
  query: string,
  options?: { sort?: string; lang?: string },
): CommandItem | null {
  const q = query.trim();
  if (!q) return null;
  const sort = options?.sort ?? "default";
  const lang = options?.lang ?? "zh";
  return {
    id: `search-articles:${q}`,
    label: `统一搜索：${q}`,
    keywords: ["search", "搜索", "q", q],
    kind: "navigate",
    href: moduleHref("search", sort, lang, q),
    group: "搜索",
    shortcut: "↵",
  };
}

export function buildWorkbenchCommands(options?: {
  sort?: string;
  lang?: string;
}): CommandItem[] {
  const sort = options?.sort ?? "default";
  const lang = options?.lang ?? "zh";
  const nav = (id: string, label: string, keywords: string[]): CommandItem => ({
    id: `nav-${id}`,
    label,
    keywords: [id, label, ...keywords],
    kind: "navigate",
    href: moduleHref(id, sort, lang),
    group: "导航",
  });

  return [
    nav("home", "今日情报", ["home", "intelligence", "情报台", "brief", "dashboard"]),
    nav("review", "划线复习", ["review", "spaced", "复习"]),
    nav("clusters", "故事线 Clusters", ["cluster", "dedupe", "故事线"]),
    nav("themes", "主题簇 Themes", ["theme", "tag", "主题"]),
    nav("research", "语料研究 Agent", ["research", "agent", "corpus", "研究"]),
    nav("search", "统一搜索", ["search", "article", "highlight", "note", "全文", "划线", "笔记"]),
    nav("rules", "规则引擎", ["rules", "mute", "boost", "规则"]),
    nav("saved-searches", "保存的搜索", ["saved", "search", "filter", "过滤器"]),
    nav("interest", "兴趣向量", ["interest", "personalization", "兴趣"]),
    nav("craft", "阅读工艺 Scan/Focus/Keep", ["craft", "density", "mode", "工艺"]),
    nav("export", "立项导出", ["export", "zip", "markdown", "导出"]),
    nav("all", "最新文章", ["feed", "信息流", "rss"]),
    nav("unread", "新到未读", ["inbox", "unread"]),
    nav("read", "已读", ["archive"]),
    nav("read-later", "继续阅读", ["later", "queue", "阅读进度"]),
    nav("starred", "候选线索", ["candidate", "saved", "star"]),
    nav("project", "已立项", ["project", "立项"]),
    nav("technical", "技术维度", ["score", "tech"]),
    nav("business", "商业维度", ["score"]),
    nav("trend", "趋势维度", ["score"]),
    nav("ai", "AI 维度", ["score"]),
    nav("product", "产品维度", ["score"]),
    nav("security", "安全维度", ["score"]),
    {
      id: "nav-admin",
      label: "管理控制台",
      keywords: ["admin", "sync", "score", "管理"],
      kind: "navigate",
      href: moduleHref("admin", sort, lang),
      group: "导航",
    },
    {
      id: "action-theme",
      label: "切换浅色 / 深色主题",
      keywords: ["theme", "dark", "light", "主题", "夜间"],
      kind: "action",
      action: "toggle-theme",
      group: "外观",
      shortcut: "T",
    },
    {
      id: "action-focus-list",
      label: "聚焦文章列表（键盘 j/k）",
      keywords: ["keyboard", "list", "j", "k", "快捷键"],
      kind: "action",
      action: "focus-list",
      group: "快捷键",
      shortcut: "G L",
    },
    {
      id: "action-cycle-mode",
      label: "切换 Scan / Focus / Keep 态",
      keywords: ["mode", "scan", "focus", "keep", "扫描", "精读", "沉淀"],
      kind: "action",
      action: "cycle-mode",
      group: "工艺",
      shortcut: "M",
    },
    {
      id: "action-toggle-density",
      label: "切换舒适 / 紧凑密度",
      keywords: ["density", "compact", "密度"],
      kind: "action",
      action: "toggle-density",
      group: "工艺",
    },
    {
      id: "action-toggle-dual-pane",
      label: "切换双栏对照",
      keywords: ["dual", "pane", "split", "双栏"],
      kind: "action",
      action: "toggle-dual-pane",
      group: "工艺",
    },
    {
      id: "action-admin-sync",
      label: "触发同步 Miniflux",
      keywords: ["sync", "同步", "miniflux"],
      kind: "action",
      action: "admin-sync",
      group: "运维",
    },
    {
      id: "action-admin-brief",
      label: "生成今日情报简报",
      keywords: ["brief", "情报", "daily"],
      kind: "action",
      action: "admin-brief",
      group: "运维",
    },
    {
      id: "action-admin-govern",
      label: "运行源治理 demote",
      keywords: ["govern", "demote", "源治理"],
      kind: "action",
      action: "admin-govern",
      group: "运维",
    },
    {
      id: "action-open-usage",
      label: "查看费用 / 用量（管理台）",
      keywords: ["usage", "budget", "费用", "余额"],
      kind: "action",
      action: "open-usage",
      group: "运维",
    },
  ];
}

export function normalizeCommandQuery(query: string): string {
  return query.trim().toLowerCase();
}

export function filterCommands(commands: CommandItem[], query: string): CommandItem[] {
  const q = normalizeCommandQuery(query);
  if (!q) return commands;
  const matched = commands.filter((command) => {
    if (command.label.toLowerCase().includes(q)) return true;
    if (command.id.toLowerCase().includes(q)) return true;
    return command.keywords.some((keyword) => keyword.toLowerCase().includes(q));
  });
  const search = searchArticlesCommand(query);
  if (search) {
    // Put unified search first so ⌘K covers corpus text and private knowledge.
    return [search, ...matched.filter((command) => command.id !== search.id)];
  }
  return matched;
}

export function moveCommandIndex(
  current: number,
  delta: number,
  length: number,
): number {
  if (length <= 0) return 0;
  return (current + delta + length) % length;
}

export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  if (target == null || typeof target !== "object") return false;
  const el = target as { isContentEditable?: boolean; tagName?: string };
  if (el.isContentEditable) return true;
  const tag = typeof el.tagName === "string" ? el.tagName.toUpperCase() : "";
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

export function isInteractiveKeyboardTarget(target: EventTarget | null): boolean {
  if (isEditableKeyboardTarget(target)) return true;
  if (target == null || typeof target !== "object") return false;
  const el = target as { closest?: (selector: string) => unknown; tagName?: string };
  if (typeof el.closest === "function") {
    return Boolean(el.closest("a, button, [role='button'], [role='dialog'], [role='listbox'], [role='menuitem'], [role='option']"));
  }
  const tag = typeof el.tagName === "string" ? el.tagName.toUpperCase() : "";
  return tag === "A" || tag === "BUTTON";
}

export function isCommandPaletteToggle(event: {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
}): boolean {
  return (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
}

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
  action?: "toggle-theme" | "focus-list";
  group: string;
  shortcut?: string;
};

export function moduleHref(
  moduleId: string,
  sort: string = "default",
  lang: string = "zh",
): string {
  const qs = new URLSearchParams({ module: moduleId, sort, lang });
  return `/?${qs.toString()}`;
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
    nav("all", "最新文章", ["home", "feed", "信息流"]),
    nav("unread", "新到未读", ["inbox", "unread"]),
    nav("read", "已读", ["archive"]),
    nav("read-later", "稍后读", ["later", "queue"]),
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
  ];
}

export function normalizeCommandQuery(query: string): string {
  return query.trim().toLowerCase();
}

export function filterCommands(commands: CommandItem[], query: string): CommandItem[] {
  const q = normalizeCommandQuery(query);
  if (!q) return commands;
  return commands.filter((command) => {
    if (command.label.toLowerCase().includes(q)) return true;
    if (command.id.toLowerCase().includes(q)) return true;
    return command.keywords.some((keyword) => keyword.toLowerCase().includes(q));
  });
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

export function isCommandPaletteToggle(event: {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
}): boolean {
  return (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
}

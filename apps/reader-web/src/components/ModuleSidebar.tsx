import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";

const MODULES: { id: string; label: string }[] = [
  { id: "all", label: "最新" },
  { id: "unread", label: "新到" },
  { id: "read", label: "已读" },
  { id: "starred", label: "候选" },
  { id: "project", label: "已立项" },
  { id: "read-later", label: "稍后读" },
  { id: "technical", label: "技术" },
  { id: "business", label: "商业" },
  { id: "trend", label: "趋势" },
  { id: "ai", label: "AI" },
  { id: "product", label: "产品" },
  { id: "security", label: "安全" },
  { id: "feeds", label: "订阅源管理" },
];

function moduleHref(moduleId: string, currentSort: ArticleSortId, currentLang: SummaryLangId) {
  const qs = new URLSearchParams({ module: moduleId, sort: currentSort, lang: currentLang });
  return `?${qs.toString()}`;
}

export function ModuleSidebar({
  currentModule,
  currentSort = "default",
  currentLang = "zh",
}: {
  currentModule: string;
  currentSort?: ArticleSortId;
  currentLang?: SummaryLangId;
}) {
  return (
    <aside className="moduleSidebar">
      <div className="brand">AI Reader</div>
      <nav className="moduleNav" aria-label="阅读模块">
        {MODULES.map((m) => {
          if (m.id === "feeds") {
            return (
              <span
                key={m.id}
                className="moduleNavLink moduleNavLinkComingSoon"
                aria-disabled="true"
                aria-label={`${m.label}，即将推出`}
              >
                {m.label}
              </span>
            );
          }
          const active = currentModule === m.id;
          return (
            <a
              key={m.id}
              className={`moduleNavLink${active ? " moduleNavLinkActive" : ""}`}
              href={moduleHref(m.id, currentSort, currentLang)}
              aria-current={active ? "page" : undefined}
            >
              {m.label}
            </a>
          );
        })}
      </nav>
    </aside>
  );
}

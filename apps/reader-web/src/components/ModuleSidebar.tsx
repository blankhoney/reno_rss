const MODULES: { id: string; label: string }[] = [
  { id: "unread", label: "未读" },
  { id: "read", label: "已读" },
  { id: "starred", label: "收藏" },
  { id: "read-later", label: "稍后读" },
  { id: "technical", label: "技术" },
  { id: "business", label: "商业" },
  { id: "trend", label: "趋势" },
  { id: "ai", label: "AI" },
  { id: "product", label: "产品" },
  { id: "security", label: "安全" },
  { id: "feeds", label: "订阅" },
];

export function ModuleSidebar({ currentModule }: { currentModule: string }) {
  return (
    <aside className="moduleSidebar">
      <div className="brand">AI Reader</div>
      <nav className="moduleNav" aria-label="阅读模块">
        {MODULES.map((m) => {
          const active = currentModule === m.id;
          return (
            <a
              key={m.id}
              className={`moduleNavLink${active ? " moduleNavLinkActive" : ""}`}
              href={`?module=${encodeURIComponent(m.id)}`}
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

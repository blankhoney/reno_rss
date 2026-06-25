"use client";

import { AnimatePresence } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import { AnimatedPanel } from "./AnimatedPanel";
import { ThemeToggle } from "./ThemeToggle";

type ModuleNavItem = { id: string; label: string; disabled?: boolean };
type ModuleNavGroup = { id: string; label: string; items: ModuleNavItem[] };

const STORAGE_KEY = "ai-reader.sidebar.collapsedGroups";
const DEFAULT_COLLAPSED_GROUPS = new Set(["scores", "manage"]);

const MODULE_GROUPS: ModuleNavGroup[] = [
  {
    id: "flow",
    label: "信息流",
    items: [
      { id: "all", label: "最新" },
      { id: "unread", label: "新到" },
      { id: "read", label: "已读" },
      { id: "read-later", label: "稍后读" },
    ],
  },
  {
    id: "clues",
    label: "线索流",
    items: [
      { id: "starred", label: "候选" },
      { id: "project", label: "已立项" },
    ],
  },
  {
    id: "scores",
    label: "评分维度",
    items: [
      { id: "technical", label: "技术" },
      { id: "business", label: "商业" },
      { id: "trend", label: "趋势" },
      { id: "ai", label: "AI" },
      { id: "product", label: "产品" },
      { id: "security", label: "安全" },
    ],
  },
  {
    id: "manage",
    label: "管理",
    items: [
      { id: "feeds", label: "订阅源管理" },
      { id: "admin", label: "管理控制台" },
    ],
  },
];

function moduleHref(moduleId: string, currentSort: ArticleSortId, currentLang: SummaryLangId) {
  const qs = new URLSearchParams({ module: moduleId, sort: currentSort, lang: currentLang });
  return `?${qs.toString()}`;
}

function activeGroupIdForModule(currentModule: string): string | null {
  return MODULE_GROUPS.find((group) => group.items.some((item) => item.id === currentModule))?.id ?? null;
}

function initialCollapsedGroups(currentModule: string): Set<string> {
  const next = new Set(DEFAULT_COLLAPSED_GROUPS);
  const activeGroupId = activeGroupIdForModule(currentModule);
  if (activeGroupId) next.delete(activeGroupId);
  return next;
}

function readStoredCollapsedGroups(): Set<string> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return new Set(parsed.map(String));
  } catch {
    return null;
  }
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
  const activeGroupId = useMemo(() => activeGroupIdForModule(currentModule), [currentModule]);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() =>
    initialCollapsedGroups(currentModule),
  );

  useEffect(() => {
    const stored = readStoredCollapsedGroups();
    if (stored) setCollapsedGroups(stored);
  }, [currentModule]);

  function toggleGroup(groupId: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
      } catch {
        // Ignore storage failures; folded state is a convenience only.
      }
      return next;
    });
  }

  return (
    <aside className="moduleSidebar">
      <div className="brandBlock">
        <div className="brandRow">
          <div className="brand">AI Reader</div>
          <ThemeToggle />
        </div>
        <a
          className="sourceLink"
          href="https://github.com/blankhoney/reno_rss"
          target="_blank"
          rel="noreferrer noopener"
        >
          GitHub 源码
        </a>
      </div>
      <nav className="moduleNav" aria-label="阅读模块">
        {MODULE_GROUPS.map((group) => {
          const collapsed = collapsedGroups.has(group.id);
          const activeGroup = activeGroupId === group.id;
          return (
            <section className="moduleNavGroup" key={group.id}>
              <button
                type="button"
                className={`moduleNavGroupButton${activeGroup ? " moduleNavGroupButtonActive" : ""}`}
                aria-expanded={!collapsed}
                onClick={() => toggleGroup(group.id)}
              >
                <span>{group.label}</span>
                <span aria-hidden="true">{collapsed ? "+" : "-"}</span>
              </button>
              <AnimatePresence initial={false}>
                {collapsed ? null : (
                  <AnimatedPanel
                    key={`${group.id}-items`}
                    variant="collapse"
                    className="moduleNavGroupItems"
                  >
                    {group.items.map((m) => {
                      if (m.disabled) {
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
                  </AnimatedPanel>
                )}
              </AnimatePresence>
            </section>
          );
        })}
      </nav>
    </aside>
  );
}

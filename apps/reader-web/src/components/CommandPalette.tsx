"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useDismissableLayer } from "./useDismissableLayer";
import {
  FOCUS_ARTICLE_LIST_EVENT,
  buildWorkbenchCommands,
  filterCommands,
  isCommandPaletteToggle,
  isEditableKeyboardTarget,
  moveCommandIndex,
  type CommandItem,
} from "@/lib/commandPalette";
import {
  cycleReaderMode,
  patchCraftPreferences,
  readCraftPreferences,
} from "@/lib/craft/preferences";
import { apiPost } from "@/lib/api/client";
import { emitToast } from "./Toast";

const THEME_STORAGE_KEY = "ai-reader.theme";

function toggleDocumentTheme() {
  if (typeof document === "undefined") return;
  const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // Preference persistence is best-effort.
  }
}

function runCommand(command: CommandItem, router: { push: (href: string) => void }) {
  if (command.kind === "navigate" && command.href) {
    router.push(command.href);
    return;
  }
  if (command.action === "toggle-theme") {
    toggleDocumentTheme();
    return;
  }
  if (command.action === "focus-list") {
    window.dispatchEvent(new Event(FOCUS_ARTICLE_LIST_EVENT));
    return;
  }
  if (command.action === "cycle-mode") {
    const prefs = readCraftPreferences();
    patchCraftPreferences({ mode: cycleReaderMode(prefs.mode) });
    return;
  }
  if (command.action === "toggle-density") {
    const prefs = readCraftPreferences();
    patchCraftPreferences({
      density: prefs.density === "compact" ? "comfortable" : "compact",
    });
    return;
  }
  if (command.action === "toggle-dual-pane") {
    const prefs = readCraftPreferences();
    patchCraftPreferences({ dualPane: !prefs.dualPane });
    return;
  }
  if (command.action === "open-usage") {
    router.push("/?module=admin&sort=default&lang=zh");
    return;
  }
  if (command.action === "admin-sync") {
    void apiPost("/api/admin/sync", { limit: 100 })
      .then(() => emitToast({ title: "已触发同步", variant: "success" }))
      .catch((error) =>
        emitToast({
          title: error instanceof Error ? error.message : "同步失败（需管理员）",
          variant: "error",
        }),
      );
    return;
  }
  if (command.action === "admin-brief") {
    void apiPost("/api/admin/daily-brief", {})
      .then(() => emitToast({ title: "已排队生成今日情报", variant: "success" }))
      .catch((error) =>
        emitToast({
          title: error instanceof Error ? error.message : "生成简报失败（需管理员）",
          variant: "error",
        }),
      );
    return;
  }
  if (command.action === "admin-govern") {
    void apiPost("/api/admin/govern-sources", {})
      .then(() => emitToast({ title: "已排队源治理 demote", variant: "success" }))
      .catch((error) =>
        emitToast({
          title: error instanceof Error ? error.message : "源治理失败（需管理员）",
          variant: "error",
        }),
      );
  }
}

export function CommandPaletteHost() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const commands = useMemo(() => buildWorkbenchCommands(), []);
  const filtered = useMemo(() => filterCommands(commands, query), [commands, query]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIndex(0);
  }, []);

  const openPalette = useCallback(() => {
    setOpen(true);
    setQuery("");
    setActiveIndex(0);
  }, []);

  useDismissableLayer({
    enabled: open,
    layerRef: dialogRef,
    onDismiss: close,
    trapFocus: true,
    initialFocusRef: inputRef,
  });

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isCommandPaletteToggle(event)) {
        event.preventDefault();
        if (open) close();
        else openPalette();
        return;
      }
      if (!open && event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        if (isEditableKeyboardTarget(event.target)) return;
        event.preventDefault();
        openPalette();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close, open, openPalette]);

  useEffect(() => {
    if (!open || rootRef.current == null) return;
    const background = Array.from(document.body.children).filter(
      (element): element is HTMLElement => element instanceof HTMLElement && element !== rootRef.current,
    );
    const previousInert = background.map((element) => [element, element.inert] as const);
    background.forEach((element) => {
      element.inert = true;
    });
    return () => {
      previousInert.forEach(([element, inert]) => {
        element.inert = inert;
      });
    };
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  function selectActive() {
    const command = filtered[activeIndex];
    if (!command) return;
    close();
    runCommand(command, router);
  }

  if (!open) return null;

  return (
    <div ref={rootRef} className="commandPaletteRoot" role="presentation">
      <div className="commandPaletteBackdrop" aria-hidden="true" />
      <div
        ref={dialogRef}
        className="commandPaletteDialog"
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
      >
        <div className="commandPaletteSearchRow">
          <input
            ref={inputRef}
            className="commandPaletteInput"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActiveIndex((index) => moveCommandIndex(index, 1, filtered.length));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActiveIndex((index) => moveCommandIndex(index, -1, filtered.length));
              } else if (event.key === "Enter") {
                event.preventDefault();
                selectActive();
              }
            }}
            placeholder="搜索命令、模块…（⌘K / Ctrl+K）"
            aria-autocomplete="list"
            aria-controls="command-palette-list"
            aria-activedescendant={filtered[activeIndex] ? `command-palette-option-${filtered[activeIndex].id}` : undefined}
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="commandPaletteKbd">esc</kbd>
        </div>
        <ul id="command-palette-list" className="commandPaletteList" role="listbox" aria-label="命令">
          {filtered.length === 0 ? (
            <li className="commandPaletteEmpty">没有匹配的命令</li>
          ) : (
            filtered.map((command, index) => {
              const active = index === activeIndex;
              return (
                <li id={`command-palette-option-${command.id}`} key={command.id} role="option" aria-selected={active}>
                  <button
                    type="button"
                    className={active ? "commandPaletteItem commandPaletteItemActive" : "commandPaletteItem"}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => {
                      close();
                      runCommand(command, router);
                    }}
                  >
                    <span className="commandPaletteItemMain">
                      <span className="commandPaletteItemLabel">{command.label}</span>
                      <span className="commandPaletteItemGroup">{command.group}</span>
                    </span>
                    {command.shortcut ? (
                      <kbd className="commandPaletteItemShortcut">{command.shortcut}</kbd>
                    ) : null}
                  </button>
                </li>
              );
            })
          )}
        </ul>
        <p className="commandPaletteHint">
          <span>↑↓ 选择</span>
          <span>↵ 执行</span>
          <span>列表 j/k 移动 · Enter 打开</span>
        </p>
      </div>
    </div>
  );
}

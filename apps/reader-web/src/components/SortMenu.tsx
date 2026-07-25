"use client";

import { AnimatePresence } from "motion/react";
import { useRef, useState } from "react";
import type { ArticleSortId } from "@/lib/articles/service";
import { moveCommandIndex } from "@/lib/commandPalette";
import { AnimatedPanel } from "./AnimatedPanel";
import { useDismissableLayer } from "./useDismissableLayer";

export type SortOption = { id: ArticleSortId; label: string };

export function SortMenu({
  currentSort,
  options,
  onChange,
}: {
  currentSort: ArticleSortId;
  options: SortOption[];
  onChange: (sort: ArticleSortId) => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = options.find((option) => option.id === currentSort) ?? options[0];

  function focusOption(index: number) {
    window.requestAnimationFrame(() => optionRefs.current[index]?.focus());
  }

  function openMenu(index = options.findIndex((option) => option.id === currentSort)) {
    const nextIndex = index >= 0 ? index : 0;
    setActiveIndex(nextIndex);
    setOpen(true);
    focusOption(nextIndex);
  }

  function closeMenu() {
    setOpen(false);
  }

  function selectOption(index: number) {
    const option = options[index];
    if (!option) return;
    closeMenu();
    if (option.id !== currentSort) onChange(option.id);
  }

  useDismissableLayer({
    enabled: open,
    layerRef: rootRef,
    ignoreRefs: [triggerRef],
    onDismiss: closeMenu,
    restoreFocusRef: triggerRef,
  });

  return (
    <div className="sortMenu" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="sortMenuButton"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls="sort-menu-options"
        onClick={() => {
          if (open) closeMenu();
          else openMenu();
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            openMenu(0);
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            openMenu(Math.max(options.length - 1, 0));
          } else if (event.key === "Home") {
            event.preventDefault();
            openMenu(0);
          } else if (event.key === "End") {
            event.preventDefault();
            openMenu(Math.max(options.length - 1, 0));
          }
        }}
      >
        <span className="sortMenuLabel">排序</span>
        <span>{current?.label ?? "默认排序"}</span>
        <span aria-hidden="true" className="sortMenuChevron">
          {open ? "↑" : "↓"}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <AnimatedPanel
            key="sort-menu"
            id="sort-menu-options"
            variant="popover"
            className="sortMenuPopover"
            role="listbox"
            aria-label="排序方式"
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActiveIndex((index) => {
                  const next = moveCommandIndex(index, 1, options.length);
                  focusOption(next);
                  return next;
                });
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActiveIndex((index) => {
                  const next = moveCommandIndex(index, -1, options.length);
                  focusOption(next);
                  return next;
                });
              } else if (event.key === "Home") {
                event.preventDefault();
                setActiveIndex(0);
                focusOption(0);
              } else if (event.key === "End") {
                event.preventDefault();
                const lastIndex = Math.max(options.length - 1, 0);
                setActiveIndex(lastIndex);
                focusOption(lastIndex);
              } else if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectOption(activeIndex);
              }
            }}
          >
            {options.map((option, index) => {
              const selected = option.id === currentSort;
              return (
                <button
                  ref={(element) => {
                    optionRefs.current[index] = element;
                  }}
                  key={option.id}
                  type="button"
                  className={`sortMenuOption${selected ? " sortMenuOptionActive" : ""}`}
                  role="option"
                  aria-selected={selected}
                  tabIndex={index === activeIndex ? 0 : -1}
                  onFocus={() => setActiveIndex(index)}
                  onClick={() => selectOption(index)}
                >
                  <span>{option.label}</span>
                  {selected ? <span aria-hidden="true">✓</span> : null}
                </button>
              );
            })}
          </AnimatedPanel>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

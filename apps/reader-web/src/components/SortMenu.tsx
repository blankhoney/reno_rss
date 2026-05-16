"use client";

import { AnimatePresence } from "motion/react";
import { useRef, useState } from "react";
import type { ArticleSortId } from "@/lib/articles/service";
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
  const rootRef = useRef<HTMLDivElement | null>(null);
  const current = options.find((option) => option.id === currentSort) ?? options[0];

  useDismissableLayer({
    enabled: open,
    layerRef: rootRef,
    onDismiss: () => setOpen(false),
  });

  return (
    <div className="sortMenu" ref={rootRef}>
      <button
        type="button"
        className="sortMenuButton"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
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
            variant="popover"
            className="sortMenuPopover"
            role="listbox"
            aria-label="排序方式"
          >
            {options.map((option) => {
              const selected = option.id === currentSort;
              return (
                <button
                  key={option.id}
                  type="button"
                  className={`sortMenuOption${selected ? " sortMenuOptionActive" : ""}`}
                  role="option"
                  aria-selected={selected}
                  onClick={() => {
                    setOpen(false);
                    if (!selected) onChange(option.id);
                  }}
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

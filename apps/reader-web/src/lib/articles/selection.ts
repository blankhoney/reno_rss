import { useEffect, useState, type RefObject } from "react";

export function selectionTextWithinContainer(
  container: Pick<HTMLElement, "contains"> | null,
  selection: Pick<Selection, "anchorNode" | "focusNode" | "rangeCount" | "toString"> | null,
): string | null {
  if (container == null || selection == null || selection.rangeCount === 0) return null;
  if (selection.anchorNode == null || selection.focusNode == null) return null;
  if (!container.contains(selection.anchorNode) || !container.contains(selection.focusNode)) return null;

  const text = selection.toString().trim();
  return text.length > 0 ? text : null;
}

export function selectionRectWithinContainer(
  container: Pick<HTMLElement, "contains"> | null,
  selection: Pick<
    Selection,
    "anchorNode" | "focusNode" | "rangeCount" | "toString" | "getRangeAt"
  > | null,
): DOMRect | null {
  if (selectionTextWithinContainer(container, selection) == null) return null;
  return selection?.getRangeAt(0).getBoundingClientRect() ?? null;
}

export function selectionPreview(text: string, limit = 36): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit)}...`;
}

export function useArticleSelection(containerRef: RefObject<HTMLElement | null>) {
  const [selectedText, setSelectedText] = useState("");
  const [selectionRect, setSelectionRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    // While dragging, keep the captured text current but never show or reposition
    // the popover: a fixed popover that appears under the moving cursor flickers and
    // can intercept the gesture, collapsing the selection on pointer release.
    function syncSelectedText() {
      const text = selectionTextWithinContainer(containerRef.current, window.getSelection());
      if (text != null) {
        setSelectedText(text);
      } else {
        // Selection collapsed or left the article: hide the popover, keep last text.
        setSelectionRect(null);
      }
    }

    // Reveal/position the popover only once the selection has settled (pointer released).
    function revealPopoverOnSettle() {
      const selection = window.getSelection();
      const text = selectionTextWithinContainer(containerRef.current, selection);
      if (text == null) return;
      setSelectedText(text);
      setSelectionRect(selectionRectWithinContainer(containerRef.current, selection));
    }

    const container = containerRef.current;
    container?.addEventListener("mouseup", revealPopoverOnSettle);
    container?.addEventListener("touchend", revealPopoverOnSettle);
    document.addEventListener("selectionchange", syncSelectedText);
    return () => {
      container?.removeEventListener("mouseup", revealPopoverOnSettle);
      container?.removeEventListener("touchend", revealPopoverOnSettle);
      document.removeEventListener("selectionchange", syncSelectedText);
    };
  }, [containerRef]);

  return {
    selectedText,
    hasSelection: selectedText.trim().length > 0,
    selectionRect,
    clearSelection: () => {
      setSelectedText("");
      setSelectionRect(null);
    },
  };
}

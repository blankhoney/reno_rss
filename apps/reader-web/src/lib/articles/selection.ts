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
    function captureSelection() {
      const selection = window.getSelection();
      const text = selectionTextWithinContainer(containerRef.current, selection);
      if (text != null) {
        setSelectedText(text);
        setSelectionRect(selectionRectWithinContainer(containerRef.current, selection));
      } else {
        setSelectionRect(null);
      }
    }

    const container = containerRef.current;
    container?.addEventListener("mouseup", captureSelection);
    document.addEventListener("selectionchange", captureSelection);
    return () => {
      container?.removeEventListener("mouseup", captureSelection);
      document.removeEventListener("selectionchange", captureSelection);
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

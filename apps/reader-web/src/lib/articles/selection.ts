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

export function selectionPreview(text: string, limit = 36): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit)}...`;
}

export function useArticleSelection(containerRef: RefObject<HTMLElement | null>) {
  const [selectedText, setSelectedText] = useState("");

  useEffect(() => {
    function captureSelection() {
      const text = selectionTextWithinContainer(containerRef.current, window.getSelection());
      if (text != null) setSelectedText(text);
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
    clearSelection: () => setSelectedText(""),
  };
}

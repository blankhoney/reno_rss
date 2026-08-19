import { useEffect, useRef, useState, type RefObject } from "react";
import {
  buildTextQuoteAnchor,
  type ArticleAnnotationAnchor,
} from "./annotationAnchor";

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

export function isSelectionDismissEvent(
  event: Pick<KeyboardEvent, "key" | "isComposing">,
): boolean {
  // Escape during IME composition cancels the composition, not the selection:
  // clearing here would silently drop the pending annotation anchor.
  return event.key === "Escape" && !event.isComposing;
}

export function selectionAnchorWithinContainer(
  container: HTMLElement | null,
  range: Range | null,
): ArticleAnnotationAnchor | null {
  if (container == null || range == null) return null;
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
    return null;
  }
  const precedingRange = range.cloneRange();
  precedingRange.selectNodeContents(container);
  precedingRange.setEnd(range.startContainer, range.startOffset);
  const start = precedingRange.toString().length;
  return buildTextQuoteAnchor(
    container.textContent ?? "",
    start,
    start + range.toString().length,
  );
}

export function useArticleSelection(
  containerRef: RefObject<HTMLElement | null>,
  anchorContentRef?: RefObject<HTMLElement | null>,
  beforeRevisionChangeRef?: RefObject<((nextRevision: number) => void) | null>,
) {
  const [selectedText, setSelectedText] = useState("");
  const [selectionRect, setSelectionRect] = useState<DOMRect | null>(null);
  const [settledAnchor, setSettledAnchor] = useState<ArticleAnnotationAnchor | null>(null);
  const [selectionRevision, setSelectionRevision] = useState(0);
  const selectionRevisionRef = useRef(0);

  useEffect(() => {
    // While dragging, keep the captured text current but never show or reposition
    // the popover: a fixed popover that appears under the moving cursor flickers and
    // can intercept the gesture, collapsing the selection on pointer release.
    function syncSelectedText() {
      if (document.activeElement?.closest(".selectionPopover, aside[aria-label=\"笔记双栏\"]") != null) return;
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
      if (selection == null) return;
      const text = selectionTextWithinContainer(containerRef.current, selection);
      if (text == null) return;
      const range = selection.getRangeAt(0).cloneRange();
      setSelectedText(text);
      const anchorSource = anchorContentRef?.current ?? containerRef.current;
      setSettledAnchor(selectionAnchorWithinContainer(anchorSource, range));
      setSelectionRect(selectionRectWithinContainer(containerRef.current, selection));
      const nextRevision = selectionRevisionRef.current + 1;
      beforeRevisionChangeRef?.current?.(nextRevision);
      selectionRevisionRef.current = nextRevision;
      setSelectionRevision(nextRevision);
    }

    function hidePopover() {
      setSelectionRect(null);
    }

    function dismissSelection(event: KeyboardEvent) {
      if (!isSelectionDismissEvent(event)) return;
      setSelectedText("");
      setSettledAnchor(null);
      setSelectionRect(null);
      window.getSelection()?.removeAllRanges();
    }

    const container = containerRef.current;
    const scrollOptions: AddEventListenerOptions = { capture: true, passive: true };
    container?.addEventListener("mouseup", revealPopoverOnSettle);
    container?.addEventListener("touchend", revealPopoverOnSettle);
    document.addEventListener("selectionchange", syncSelectedText);
    document.addEventListener("scroll", hidePopover, scrollOptions);
    document.addEventListener("keydown", dismissSelection);
    window.addEventListener("resize", hidePopover);
    return () => {
      container?.removeEventListener("mouseup", revealPopoverOnSettle);
      container?.removeEventListener("touchend", revealPopoverOnSettle);
      document.removeEventListener("selectionchange", syncSelectedText);
      document.removeEventListener("scroll", hidePopover, scrollOptions);
      document.removeEventListener("keydown", dismissSelection);
      window.removeEventListener("resize", hidePopover);
    };
  }, [containerRef, anchorContentRef]);

  return {
    selectedText,
    hasSelection: selectedText.trim().length > 0,
    selectionRect,
    settledAnchor,
    selectionRevision,
    clearSelection: () => {
      setSelectedText("");
      setSettledAnchor(null);
      setSelectionRect(null);
      window.getSelection()?.removeAllRanges();
    },
  };
}

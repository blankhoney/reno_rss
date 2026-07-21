"use client";

import { useEffect, useRef, type RefObject } from "react";

type DismissableLayerOptions = {
  enabled: boolean;
  layerRef: RefObject<HTMLElement | null>;
  ignoreRefs?: RefObject<HTMLElement | null>[];
  onDismiss: () => void;
  trapFocus?: boolean;
  initialFocusRef?: RefObject<HTMLElement | null>;
  restoreFocusRef?: RefObject<HTMLElement | null>;
};

const EMPTY_REFS: RefObject<HTMLElement | null>[] = [];
const ACTIVE_LAYERS: HTMLElement[] = [];
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function eventTargetIsInside(target: EventTarget | null, ref: RefObject<HTMLElement | null>) {
  return target instanceof Node && ref.current?.contains(target);
}

function isTopmostLayer(layer: HTMLElement | null): boolean {
  return layer != null && ACTIVE_LAYERS.at(-1) === layer;
}

function focusableElements(layer: HTMLElement): HTMLElement[] {
  return Array.from(layer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => !element.hasAttribute("inert") && element.getClientRects().length > 0,
  );
}

export function useDismissableLayer({
  enabled,
  layerRef,
  ignoreRefs,
  onDismiss,
  trapFocus = false,
  initialFocusRef,
  restoreFocusRef,
}: DismissableLayerOptions) {
  const onDismissRef = useRef(onDismiss);
  const ignoreRefsRef = useRef(ignoreRefs ?? EMPTY_REFS);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  onDismissRef.current = onDismiss;
  ignoreRefsRef.current = ignoreRefs ?? EMPTY_REFS;

  useEffect(() => {
    if (!enabled) return;
    const layer = layerRef.current;
    if (layer == null) return;
    ACTIVE_LAYERS.push(layer);

    const onPointerDown = (event: PointerEvent) => {
      if (!isTopmostLayer(layer)) return;
      if (eventTargetIsInside(event.target, layerRef)) return;
      if (ignoreRefsRef.current.some((ref) => eventTargetIsInside(event.target, ref))) return;
      onDismissRef.current();
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (!isTopmostLayer(layer)) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onDismissRef.current();
        return;
      }
      if (!trapFocus || event.key !== "Tab") return;

      const focusable = focusableElements(layer);
      if (focusable.length === 0) {
        event.preventDefault();
        layer.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown);
      const index = ACTIVE_LAYERS.lastIndexOf(layer);
      if (index !== -1) ACTIVE_LAYERS.splice(index, 1);
    };
  }, [enabled, layerRef, trapFocus]);

  useEffect(() => {
    if (!enabled) return;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      (initialFocusRef?.current ?? layerRef.current)?.focus();
    });

    return () => {
      window.cancelAnimationFrame(frame);
      const target = restoreFocusRef?.current ?? previousFocusRef.current;
      if (target?.isConnected) {
        window.requestAnimationFrame(() => target.focus());
      }
    };
  }, [enabled, initialFocusRef, layerRef, restoreFocusRef]);
}

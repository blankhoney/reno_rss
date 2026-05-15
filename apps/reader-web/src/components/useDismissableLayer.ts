"use client";

import { useEffect, type RefObject } from "react";

type DismissableLayerOptions = {
  enabled: boolean;
  layerRef: RefObject<HTMLElement | null>;
  ignoreRefs?: RefObject<HTMLElement | null>[];
  onDismiss: () => void;
};

const EMPTY_REFS: RefObject<HTMLElement | null>[] = [];

function eventTargetIsInside(target: EventTarget | null, ref: RefObject<HTMLElement | null>) {
  return target instanceof Node && ref.current?.contains(target);
}

export function useDismissableLayer({
  enabled,
  layerRef,
  ignoreRefs,
  onDismiss,
}: DismissableLayerOptions) {
  useEffect(() => {
    if (!enabled) return;
    const refsToIgnore = ignoreRefs ?? EMPTY_REFS;

    const onPointerDown = (event: PointerEvent) => {
      if (eventTargetIsInside(event.target, layerRef)) return;
      if (refsToIgnore.some((ref) => eventTargetIsInside(event.target, ref))) return;
      onDismiss();
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      onDismiss();
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [enabled, ignoreRefs, layerRef, onDismiss]);
}

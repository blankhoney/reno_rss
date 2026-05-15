"use client";

import type { ReactNode } from "react";
import { MotionConfig } from "motion/react";

export function MotionRoot({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: 0.18, ease: "easeOut" }}>
      {children}
    </MotionConfig>
  );
}

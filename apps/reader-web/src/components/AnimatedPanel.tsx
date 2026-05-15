"use client";

import type { CSSProperties, ReactNode } from "react";
import { motion, type HTMLMotionProps } from "motion/react";

type AnimatedPanelVariant = "popover" | "collapse";

const panelVariants = {
  popover: {
    initial: { opacity: 0, y: -6, scale: 0.985 },
    animate: { opacity: 1, y: 0, scale: 1 },
    exit: { opacity: 0, y: -4, scale: 0.985 },
  },
  collapse: {
    initial: { opacity: 0, height: 0 },
    animate: { opacity: 1, height: "auto" },
    exit: { opacity: 0, height: 0 },
  },
} as const;

export function AnimatedPanel({
  variant,
  children,
  className,
  style,
  ...props
}: {
  variant: AnimatedPanelVariant;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
} & Omit<HTMLMotionProps<"div">, "children" | "className" | "style">) {
  const motionProps = panelVariants[variant];
  return (
    <motion.div
      {...motionProps}
      {...props}
      className={className}
      style={{ overflow: variant === "collapse" ? "hidden" : undefined, ...style }}
    >
      {children}
    </motion.div>
  );
}

"use client";

import type { CSSProperties } from "react";

type ScoreRingSize = 46 | 52 | 66;

type ScoreRingStyle = CSSProperties & {
  "--ringFill"?: string;
  "--ringColor"?: string;
};

export function tierLabel(tier: string | null | undefined): string | null {
  if (tier === "must_read") return "必读";
  if (tier === "read") return "推荐";
  if (tier === "skim") return "略读";
  if (tier === "skip") return "跳过";
  return tier ?? null;
}

export function tierColorVar(tier: string | null | undefined, value?: number | null): string {
  if (tier === "must_read") return "--accent";
  if (tier === "read") return "--success";
  if (tier === "skim") return "--warning";
  if (tier === "skip") return "--text-soft";
  if (typeof value !== "number" || !Number.isFinite(value)) return "--border-strong";
  if (value >= 70) return "--success";
  if (value >= 45) return "--accent";
  return "--warning";
}

function normalizeScore(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function ScoreRing({
  value,
  tier = null,
  size = 52,
  label,
}: {
  value: number | null | undefined;
  tier?: string | null;
  size?: ScoreRingSize;
  label?: string;
}) {
  const normalized = normalizeScore(value);
  const isEmpty = normalized == null;
  const ariaLabel = isEmpty ? "未评分" : `${label ?? "总分"} ${normalized}`;
  const style: ScoreRingStyle | undefined = isEmpty
    ? undefined
    : {
        "--ringFill": `${normalized}%`,
        "--ringColor": `var(${tierColorVar(tier, normalized)})`,
      };

  return (
    <span
      className={`scoreRing scoreRing${size}${isEmpty ? " scoreRingEmpty" : ""}`}
      role="img"
      aria-label={ariaLabel}
      style={style}
    >
      <span className="scoreRingValue">{isEmpty ? "—" : normalized}</span>
    </span>
  );
}

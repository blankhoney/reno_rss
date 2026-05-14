export type ScoringSettings = {
  autoScoreNewUnread: boolean;
  webhookMaxEntries: number;
  manualBatchSize: number;
  manualRescoreEnabled: boolean;
};

export const DEFAULT_SCORING_SETTINGS: ScoringSettings = {
  autoScoreNewUnread: true,
  webhookMaxEntries: 20,
  manualBatchSize: 20,
  manualRescoreEnabled: true,
};

export function clampInt(value: unknown, min: number, max: number, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

export function normalizeScoringSettingsPatch(input: unknown): ScoringSettings {
  const record =
    input !== null && typeof input === "object" && !Array.isArray(input)
      ? (input as Record<string, unknown>)
      : {};
  return {
    autoScoreNewUnread:
      typeof record.autoScoreNewUnread === "boolean"
        ? record.autoScoreNewUnread
        : DEFAULT_SCORING_SETTINGS.autoScoreNewUnread,
    webhookMaxEntries: clampInt(
      record.webhookMaxEntries,
      1,
      100,
      DEFAULT_SCORING_SETTINGS.webhookMaxEntries,
    ),
    manualBatchSize: clampInt(
      record.manualBatchSize,
      1,
      50,
      DEFAULT_SCORING_SETTINGS.manualBatchSize,
    ),
    manualRescoreEnabled:
      typeof record.manualRescoreEnabled === "boolean"
        ? record.manualRescoreEnabled
        : DEFAULT_SCORING_SETTINGS.manualRescoreEnabled,
  };
}

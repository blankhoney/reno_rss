/** Persistent craft prefs: Scan/Focus/Keep mode, density, dual-pane, pinned themes. */

export type ReaderMode = "scan" | "focus" | "keep";
export type DensityMode = "comfortable" | "compact";

export type DualPaneKind = "notes" | "article";

export type CraftPreferences = {
  mode: ReaderMode;
  density: DensityMode;
  dualPane: boolean;
  dualPaneKind: DualPaneKind;
  dualArticleId: number | null;
  pinnedThemes: string[];
};

const STORAGE_KEY = "ai-reader.craft.preferences";

export const DEFAULT_CRAFT_PREFERENCES: CraftPreferences = {
  mode: "scan",
  density: "comfortable",
  dualPane: false,
  dualPaneKind: "notes",
  dualArticleId: null,
  pinnedThemes: [],
};

export function isReaderMode(value: unknown): value is ReaderMode {
  return value === "scan" || value === "focus" || value === "keep";
}

export function isDensityMode(value: unknown): value is DensityMode {
  return value === "comfortable" || value === "compact";
}

export function parseCraftPreferences(raw: unknown): CraftPreferences {
  if (raw == null || typeof raw !== "object") return { ...DEFAULT_CRAFT_PREFERENCES };
  const data = raw as Record<string, unknown>;
  const pinned = Array.isArray(data.pinnedThemes)
    ? data.pinnedThemes.map(String).filter(Boolean).slice(0, 20)
    : [];
  const dualArticleRaw = data.dualArticleId;
  const dualArticleId =
    typeof dualArticleRaw === "number" && Number.isFinite(dualArticleRaw) && dualArticleRaw > 0
      ? Math.floor(dualArticleRaw)
      : null;
  return {
    mode: isReaderMode(data.mode) ? data.mode : DEFAULT_CRAFT_PREFERENCES.mode,
    density: isDensityMode(data.density) ? data.density : DEFAULT_CRAFT_PREFERENCES.density,
    dualPane: data.dualPane === true,
    dualPaneKind: data.dualPaneKind === "article" ? "article" : "notes",
    dualArticleId,
    pinnedThemes: pinned,
  };
}

export function readCraftPreferences(): CraftPreferences {
  if (typeof window === "undefined") return { ...DEFAULT_CRAFT_PREFERENCES };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_CRAFT_PREFERENCES };
    return parseCraftPreferences(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_CRAFT_PREFERENCES };
  }
}

export function writeCraftPreferences(prefs: CraftPreferences): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  window.document.documentElement.dataset.readerMode = prefs.mode;
  window.document.documentElement.dataset.density = prefs.density;
  window.document.documentElement.dataset.dualPane = prefs.dualPane ? "true" : "false";
  window.dispatchEvent(new CustomEvent("ai-reader:craft-prefs", { detail: prefs }));
}

export function patchCraftPreferences(patch: Partial<CraftPreferences>): CraftPreferences {
  const next = { ...readCraftPreferences(), ...patch };
  if (patch.pinnedThemes) {
    next.pinnedThemes = patch.pinnedThemes.map(String).filter(Boolean).slice(0, 20);
  }
  writeCraftPreferences(next);
  return next;
}

export function modeLabel(mode: ReaderMode): string {
  if (mode === "scan") return "扫描 Scan";
  if (mode === "focus") return "精读 Focus";
  return "沉淀 Keep";
}

export function cycleReaderMode(mode: ReaderMode): ReaderMode {
  if (mode === "scan") return "focus";
  if (mode === "focus") return "keep";
  return "scan";
}

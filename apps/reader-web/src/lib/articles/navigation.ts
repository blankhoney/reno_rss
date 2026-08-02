const MAX_CURSOR_TRAIL_LENGTH = 24;
const MAX_CURSOR_LENGTH = 4096;

/**
 * Accept only the complete decimal route segment; parseInt would silently
 * alias malformed paths such as `/read/7abc` to article 7.
 */
export function parseArticleId(raw: string): number | null {
  if (!/^\d+$/.test(raw)) return null;
  const articleId = Number(raw);
  return Number.isSafeInteger(articleId) && articleId > 0 ? articleId : null;
}

export type WorkbenchNavigationContext = {
  module: string;
  sort: string;
  lang: string;
  query?: string;
  cursorStack?: (string | null)[];
  articleId?: number | null;
};

export function normalizeCursorTrail(value: unknown): (string | null)[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_CURSOR_TRAIL_LENGTH) {
    return [null];
  }
  if (value[0] !== null) return [null];

  const trail: (string | null)[] = [null];
  for (const cursor of value.slice(1)) {
    if (typeof cursor !== "string" || cursor.length === 0 || cursor.length > MAX_CURSOR_LENGTH) {
      return [null];
    }
    trail.push(cursor);
  }
  return trail;
}

export function parseCursorTrail(raw: string | null | undefined): (string | null)[] {
  if (raw == null || raw === "") return [null];
  try {
    return normalizeCursorTrail(JSON.parse(raw));
  } catch {
    return [null];
  }
}

export function serializeCursorTrail(cursorStack: (string | null)[]): string | null {
  const trail = normalizeCursorTrail(cursorStack);
  return trail.length > 1 ? JSON.stringify(trail) : null;
}

export function buildWorkbenchHref({
  module,
  sort,
  lang,
  query = "",
  cursorStack = [null],
  articleId = null,
}: WorkbenchNavigationContext): string {
  const params = new URLSearchParams({ module, sort, lang });
  const normalizedQuery = query.trim();
  if (normalizedQuery !== "") params.set("q", normalizedQuery);

  const trail = serializeCursorTrail(cursorStack);
  if (trail != null) params.set("trail", trail);
  if (articleId != null && Number.isSafeInteger(articleId) && articleId > 0) {
    params.set("article", String(articleId));
  }
  return `?${params.toString()}`;
}

export function buildFocusReadHref(articleId: number, context: WorkbenchNavigationContext): string {
  return `/read/${articleId}${buildWorkbenchHref(context)}`;
}

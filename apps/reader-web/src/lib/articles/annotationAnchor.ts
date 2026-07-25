export type ArticleAnnotationAnchor = {
  kind: "text-quote";
  version: 1;
  exact: string;
  prefix: string;
  suffix: string;
  start: number;
  end: number;
};

export type TextQuoteAnchorResolution =
  | { status: "resolved"; start: number; end: number }
  | { status: "ambiguous" }
  | { status: "not-found" };

const MAX_EXACT_LENGTH = 4_000;
const MAX_CONTEXT_LENGTH = 160;

export function buildTextQuoteAnchor(
  text: string,
  selectionStart: number,
  selectionEnd: number,
  contextLength = 64,
): ArticleAnnotationAnchor | null {
  if (!Number.isSafeInteger(selectionStart) || !Number.isSafeInteger(selectionEnd)) return null;
  if (selectionStart < 0 || selectionEnd <= selectionStart || selectionEnd > text.length) return null;

  const rawExact = text.slice(selectionStart, selectionEnd);
  const leadingWhitespace = rawExact.length - rawExact.trimStart().length;
  const exact = rawExact.trim();
  if (exact.length === 0 || exact.length > MAX_EXACT_LENGTH) return null;

  const start = selectionStart + leadingWhitespace;
  const end = start + exact.length;
  const boundedContext = Math.max(0, Math.min(MAX_CONTEXT_LENGTH, Math.trunc(contextLength)));
  return {
    kind: "text-quote",
    version: 1,
    exact,
    prefix: text.slice(Math.max(0, start - boundedContext), start),
    suffix: text.slice(end, Math.min(text.length, end + boundedContext)),
    start,
    end,
  };
}

export function parseTextQuoteAnchor(value: unknown): ArticleAnnotationAnchor | null {
  if (value == null || typeof value !== "object" || Array.isArray(value)) return null;
  const item = value as Record<string, unknown>;
  if (item.kind !== "text-quote" || item.version !== 1) return null;
  if (
    typeof item.exact !== "string" ||
    item.exact.length === 0 ||
    item.exact.length > MAX_EXACT_LENGTH ||
    typeof item.prefix !== "string" ||
    item.prefix.length > MAX_CONTEXT_LENGTH ||
    typeof item.suffix !== "string" ||
    item.suffix.length > MAX_CONTEXT_LENGTH ||
    !Number.isSafeInteger(item.start) ||
    !Number.isSafeInteger(item.end)
  ) {
    return null;
  }
  const start = item.start as number;
  const end = item.end as number;
  if (start < 0 || end <= start) return null;
  return {
    kind: "text-quote",
    version: 1,
    exact: item.exact,
    prefix: item.prefix,
    suffix: item.suffix,
    start,
    end,
  };
}

/**
 * Reattach a persisted quote only when its stored context identifies one
 * current occurrence. Exact text alone is deliberately insufficient: feeds
 * commonly repeat labels, quotes, and boilerplate after a refresh.
 */
export function resolveTextQuoteAnchor(
  text: string,
  anchor: ArticleAnnotationAnchor,
): TextQuoteAnchorResolution {
  const matches: number[] = [];
  let fromIndex = 0;
  while (fromIndex <= text.length - anchor.exact.length) {
    const start = text.indexOf(anchor.exact, fromIndex);
    if (start === -1) break;
    matches.push(start);
    fromIndex = start + Math.max(1, anchor.exact.length);
  }

  if (matches.length === 0) return { status: "not-found" };

  const contextualMatches = matches.filter((start) => {
    const end = start + anchor.exact.length;
    const prefixMatches = anchor.prefix.length === 0 || text.slice(Math.max(0, start - anchor.prefix.length), start) === anchor.prefix;
    const suffixMatches = anchor.suffix.length === 0 || text.slice(end, end + anchor.suffix.length) === anchor.suffix;
    return prefixMatches && suffixMatches;
  });

  if (contextualMatches.length !== 1) {
    return { status: contextualMatches.length === 0 ? "not-found" : "ambiguous" };
  }

  const start = contextualMatches[0];
  return { status: "resolved", start, end: start + anchor.exact.length };
}

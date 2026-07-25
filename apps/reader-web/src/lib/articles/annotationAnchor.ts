export type ArticleAnnotationAnchor = {
  kind: "text-quote";
  version: 1;
  exact: string;
  prefix: string;
  suffix: string;
  start: number;
  end: number;
};

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

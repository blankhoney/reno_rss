/** Apply private highlight marks over sanitized article HTML (GOAL §4.C). */

import {
  resolveTextQuoteAnchor,
  type ArticleAnnotationAnchor,
} from "./annotationAnchor";

export type HighlightMark = {
  id: number;
  selectedText: string;
  color: string | null;
  anchor?: ArticleAnnotationAnchor | null;
};

export type HighlightApplication = {
  html: string;
  unresolvedAnnotationIds: number[];
};

const COLOR_CLASS: Record<string, string> = {
  yellow: "hl-yellow",
  green: "hl-green",
  blue: "hl-blue",
  pink: "hl-pink",
  orange: "hl-orange",
  purple: "hl-purple",
};

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function colorClassFor(color: string | null | undefined): string {
  if (!color) return "hl-yellow";
  return COLOR_CLASS[color] ?? "hl-yellow";
}

/**
 * Apply marks over sanitized article HTML. Persisted anchors take precedence;
 * legacy unanchored records keep their historical first-match behavior.
 */
export function applyHighlightMarks(html: string, marks: HighlightMark[]): string {
  return applyHighlightMarksWithResolution(html, marks).html;
}

function textContentWithOffsets(html: string): { text: string; offsets: number[] } {
  let text = "";
  const offsets: number[] = [];
  let inTag = false;
  for (let index = 0; index < html.length; index += 1) {
    const character = html[index];
    if (character === "<") {
      inTag = true;
      continue;
    }
    if (character === ">") {
      inTag = false;
      continue;
    }
    if (inTag) continue;
    text += character;
    offsets.push(index);
  }
  return { text, offsets };
}

function wrapResolvedRange(
  html: string,
  start: number,
  end: number,
  mark: HighlightMark,
): string | null {
  const { text, offsets } = textContentWithOffsets(html);
  if (text.slice(start, end) !== mark.anchor?.exact) return null;
  const htmlStart = offsets[start];
  const htmlEnd = offsets[end - 1];
  if (htmlStart == null || htmlEnd == null) return null;
  const selectedHtml = html.slice(htmlStart, htmlEnd + 1);
  // Do not cross markup or decode entities implicitly: a partial wrapper would
  // be worse than preserving the annotation as explicitly unresolved.
  if (selectedHtml !== mark.anchor.exact) return null;
  const className = colorClassFor(mark.color);
  return `${html.slice(0, htmlStart)}<mark class="articleHighlight ${className}" data-annotation-id="${mark.id}">${selectedHtml}</mark>${html.slice(htmlEnd + 1)}`;
}

/**
 * Anchor-aware marks use the persisted quote context. Legacy marks without an
 * anchor retain the old first-match behavior for backward compatibility.
 */
export function applyHighlightMarksWithResolution(html: string, marks: HighlightMark[]): HighlightApplication {
  if (!html || marks.length === 0) return { html, unresolvedAnnotationIds: [] };
  let next = html;
  const unresolvedAnnotationIds: number[] = [];
  // Longer quotes first so nested fragments don't steal matches.
  const ordered = [...marks]
    .filter((mark) => mark.selectedText.trim().length >= 2)
    .sort((a, b) => b.selectedText.length - a.selectedText.length);
  for (const mark of ordered) {
    const quote = mark.selectedText.trim();
    if (!quote || next.includes(`data-annotation-id="${mark.id}"`)) continue;
    if (mark.anchor) {
      const resolution = resolveTextQuoteAnchor(textContentWithOffsets(next).text, mark.anchor);
      if (resolution.status !== "resolved") {
        unresolvedAnnotationIds.push(mark.id);
        continue;
      }
      const resolved = wrapResolvedRange(next, resolution.start, resolution.end, mark);
      if (resolved == null) {
        unresolvedAnnotationIds.push(mark.id);
      } else {
        next = resolved;
      }
      continue;
    }
    const className = colorClassFor(mark.color);
    const pattern = new RegExp(`(?![^<]*>)(${escapeRegExp(quote)})`);
    next = next.replace(
      pattern,
      `<mark class="articleHighlight ${className}" data-annotation-id="${mark.id}">$1</mark>`,
    );
  }
  return { html: next, unresolvedAnnotationIds };
}

export function highlightLegend(marks: HighlightMark[]): string {
  const colors = new Set(marks.map((mark) => mark.color || "yellow"));
  return [...colors].join(", ");
}

export function escapeHighlightPreview(text: string): string {
  return escapeHtml(text);
}

/** Apply private highlight marks over sanitized article HTML (GOAL §4.C). */

export type HighlightMark = {
  id: number;
  selectedText: string;
  color: string | null;
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
 * Wrap first occurrence of each selected_text in a <mark>. HTML is assumed
 * already sanitized; marks only wrap plain-text matches outside existing tags.
 */
export function applyHighlightMarks(html: string, marks: HighlightMark[]): string {
  if (!html || marks.length === 0) return html;
  let next = html;
  // Longer quotes first so nested fragments don't steal matches.
  const ordered = [...marks]
    .filter((mark) => mark.selectedText.trim().length >= 2)
    .sort((a, b) => b.selectedText.length - a.selectedText.length);
  for (const mark of ordered) {
    const quote = mark.selectedText.trim();
    if (!quote || next.includes(`data-annotation-id="${mark.id}"`)) continue;
    const className = colorClassFor(mark.color);
    const pattern = new RegExp(`(?![^<]*>)(${escapeRegExp(quote)})`);
    next = next.replace(
      pattern,
      `<mark class="articleHighlight ${className}" data-annotation-id="${mark.id}">$1</mark>`,
    );
  }
  return next;
}

export function highlightLegend(marks: HighlightMark[]): string {
  const colors = new Set(marks.map((mark) => mark.color || "yellow"));
  return [...colors].join(", ");
}

export function escapeHighlightPreview(text: string): string {
  return escapeHtml(text);
}

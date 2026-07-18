"""Extract grounded citation quotes from agent answers (GOAL Research Agent)."""

from __future__ import annotations

from dataclasses import dataclass
import re


_QUOTE_RE = re.compile(r"[「\"“](.{8,240}?)[」\"”]")
_SINGLE_QUOTE_RE = re.compile(r"'([^']{8,240})'")
MIN_QUOTE_CHARS = 8


@dataclass(frozen=True)
class Citation:
    quote: str
    start_hint: int


def extract_citation_candidates(
    article_text: str,
    answer: str,
    *,
    selected_text: str | None = None,
    limit: int = 8,
) -> list[Citation]:
    """Find quoted (or selected) substrings from the answer that appear in the article."""
    body = article_text or ""
    found: list[Citation] = []
    seen: set[str] = set()

    def _push(raw_quote: str) -> None:
        quote = (raw_quote or "").strip()
        if len(quote) < MIN_QUOTE_CHARS or quote in seen:
            return
        idx = body.find(quote)
        if idx < 0:
            collapsed = re.sub(r"\s+", "", quote)
            collapsed_body = re.sub(r"\s+", "", body)
            cidx = collapsed_body.find(collapsed)
            if cidx < 0:
                return
            idx = max(0, cidx)
        seen.add(quote)
        found.append(Citation(quote=quote, start_hint=idx))

    for match in _QUOTE_RE.finditer(answer or ""):
        _push(match.group(1))
        if len(found) >= limit:
            return found[:limit]
    for match in _SINGLE_QUOTE_RE.finditer(answer or ""):
        _push(match.group(1))
        if len(found) >= limit:
            return found[:limit]
    if selected_text:
        _push(selected_text)
    return found[:limit]

"""Encode optional highlight color + tags into annotation content (GOAL §4.C).

Stored as a single leading meta line so older rows remain readable without a
mandatory schema migration. Public API peels the meta off for clients.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


ALLOWED_COLORS = frozenset({"yellow", "green", "blue", "pink", "orange", "purple"})
_META_RE = re.compile(r"^⟦meta:(?P<body>\{.*?\})⟧\n?", re.DOTALL)


@dataclass(frozen=True)
class AnnotationMeta:
    body: str
    color: str | None = None
    tags: tuple[str, ...] = ()


def normalize_color(value: object) -> str | None:
    if value is None:
        return None
    color = str(value).strip().lower()
    if not color:
        return None
    if color not in ALLOWED_COLORS:
        raise ValueError(f"unsupported color: {color!r}")
    return color


def normalize_tags(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        raw_items = [str(item).strip() for item in value]
    else:
        raise ValueError("tags must be a list or comma-separated string")
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(item[:40])
        if len(tags) >= 12:
            break
    return tags


def encode_annotation_content(
    content: str,
    *,
    color: str | None = None,
    tags: list[str] | None = None,
) -> str:
    body = (content or "").strip()
    color_norm = normalize_color(color)
    tags_norm = normalize_tags(tags)
    if not color_norm and not tags_norm:
        return body
    payload: dict[str, object] = {}
    if color_norm:
        payload["color"] = color_norm
    if tags_norm:
        payload["tags"] = tags_norm
    return f"⟦meta:{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}⟧\n{body}"


def decode_annotation_content(content: str) -> AnnotationMeta:
    text = content or ""
    match = _META_RE.match(text)
    if not match:
        return AnnotationMeta(body=text)
    try:
        payload = json.loads(match.group("body"))
    except json.JSONDecodeError:
        return AnnotationMeta(body=text)
    if not isinstance(payload, dict):
        return AnnotationMeta(body=text)
    color = None
    try:
        color = normalize_color(payload.get("color"))
    except ValueError:
        color = None
    try:
        tags = tuple(normalize_tags(payload.get("tags")))
    except ValueError:
        tags = ()
    body = text[match.end() :]
    return AnnotationMeta(body=body, color=color, tags=tags)

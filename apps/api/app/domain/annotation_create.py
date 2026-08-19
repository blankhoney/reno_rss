from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from app.domain.annotations_meta import encode_annotation_content


ANNOTATION_CREATE_SCHEMA = "annotation-create:v1"


@dataclass(frozen=True)
class PreparedAnnotationCreate:
    content: str
    selected_text: str | None
    annotation_type: str
    color: str | None
    tags: tuple[str, ...]
    anchor: dict[str, object] | None
    stored_content: str
    request_fingerprint: str


def prepare_annotation_create(
    *,
    content: str,
    selected_text: str | None,
    annotation_type: str,
    color: str | None,
    tags: list[str],
    anchor: Mapping[str, object] | None,
) -> PreparedAnnotationCreate:
    normalized_anchor = dict(anchor) if anchor is not None else None
    canonical = {
        "schema": ANNOTATION_CREATE_SCHEMA,
        "type": annotation_type,
        "body": content,
        "color": color,
        "tags": tags,
        "selected_text": selected_text,
        "anchor": normalized_anchor,
    }
    canonical_json = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    stored_content = encode_annotation_content(
        content,
        color=color,
        tags=tags,
        anchor=normalized_anchor,
    )
    return PreparedAnnotationCreate(
        content=content,
        selected_text=selected_text,
        annotation_type=annotation_type,
        color=color,
        tags=tuple(tags),
        anchor=normalized_anchor,
        stored_content=stored_content,
        request_fingerprint=fingerprint,
    )

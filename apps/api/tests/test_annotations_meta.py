from app.domain.annotations_meta import (
    decode_annotation_content,
    encode_annotation_content,
    normalize_color,
    rewrite_annotation_content,
    searchable_annotation_body,
)


def test_encode_decode_roundtrip_color_and_tags():
    stored = encode_annotation_content("重要洞见", color="yellow", tags=["ai", "rust", "ai"])
    assert stored.startswith("⟦meta:")
    meta = decode_annotation_content(stored)
    assert meta.body == "重要洞见"
    assert meta.color == "yellow"
    assert meta.tags == ("ai", "rust")


def test_encode_decode_roundtrip_anchor_without_color_or_tags():
    anchor = {
        "kind": "text-quote",
        "version": 1,
        "exact": "重要洞见",
        "prefix": "前文",
        "suffix": "后文",
        "start": 4,
        "end": 8,
    }

    stored = encode_annotation_content("重要洞见", anchor=anchor)
    meta = decode_annotation_content(stored)

    assert stored.startswith("⟦meta:")
    assert meta.body == "重要洞见"
    assert meta.anchor == anchor


def test_plain_content_has_no_meta():
    meta = decode_annotation_content("just a note")
    assert meta.body == "just a note"
    assert meta.color is None
    assert meta.tags == ()
    assert meta.anchor is None


def test_normalize_color_rejects_unknown():
    try:
        normalize_color("neon")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unsupported color" in str(exc)


def test_rewrite_preserves_anchor_and_replaces_editable_metadata():
    anchor = {
        "kind": "text-quote",
        "version": 1,
        "exact": "原选区",
        "prefix": "前",
        "suffix": "后",
        "start": 2,
        "end": 5,
    }
    stored = encode_annotation_content("旧正文", color="yellow", tags=["Old"], anchor=anchor)

    rewritten = rewrite_annotation_content(
        stored,
        "  新正文  ",
        color="BLUE",
        tags=["AI", "ai", "research", " ", "AI"],
    )
    meta = decode_annotation_content(rewritten)

    assert meta.body == "新正文"
    assert meta.color == "blue"
    assert meta.tags == ("AI", "research")
    assert meta.anchor == anchor
    assert "旧正文" not in rewritten
    assert "yellow" not in rewritten


def test_rewrite_rejects_blank_body():
    try:
        rewrite_annotation_content("plain note", "  ")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "content is required"


def test_rewrite_plain_history_can_clear_meta():
    rewritten = rewrite_annotation_content(
        encode_annotation_content("old", color="green", tags=["legacy"]),
        "new",
        color=None,
        tags=[],
    )

    assert rewritten == "new"
    assert decode_annotation_content(rewritten).anchor is None


def test_normalize_tags_deduplicates_case_insensitively_and_caps_items():
    from app.domain.annotations_meta import normalize_tags

    tags = normalize_tags(["one", "ONE", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"])

    assert tags == ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]


def test_searchable_annotation_body_excludes_encoded_meta():
    stored = encode_annotation_content(
        "current body",
        anchor={
            "kind": "text-quote",
            "version": 1,
            "exact": "old body",
            "prefix": "",
            "suffix": "",
            "start": 0,
            "end": 8,
        },
    )

    assert searchable_annotation_body(stored) == "current body"


def test_prepare_annotation_create_fingerprint_is_canonical_and_field_sensitive():
    from app.domain.annotation_create import prepare_annotation_create

    anchor = {
        "kind": "text-quote",
        "version": 1,
        "exact": "quoted",
        "prefix": "before",
        "suffix": "after",
        "start": 4,
        "end": 10,
    }
    first = prepare_annotation_create(
        content="note",
        selected_text="quoted",
        annotation_type="comment",
        color="yellow",
        tags=["ai", "research"],
        anchor=anchor,
    )
    reordered = prepare_annotation_create(
        anchor={"end": 10, "start": 4, "suffix": "after", "prefix": "before", "exact": "quoted", "version": 1, "kind": "text-quote"},
        content="note",
        selected_text="quoted",
        annotation_type="comment",
        color="yellow",
        tags=["ai", "research"],
    )
    assert first.request_fingerprint == reordered.request_fingerprint
    assert first.stored_content != first.content
    assert all(
        prepare_annotation_create(
            content="changed" if field == "content" else first.content,
            selected_text="changed" if field == "selected_text" else first.selected_text,
            annotation_type="annotation" if field == "type" else first.annotation_type,
            color="blue" if field == "color" else first.color,
            tags=["other"] if field == "tags" else list(first.tags),
            anchor=None if field == "anchor" else anchor,
        ).request_fingerprint != first.request_fingerprint
        for field in ("content", "selected_text", "type", "color", "tags", "anchor")
    )
    assert first.anchor == anchor
    assert first.tags == ("ai", "research")

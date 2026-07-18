from app.domain.annotations_meta import (
    decode_annotation_content,
    encode_annotation_content,
    normalize_color,
)


def test_encode_decode_roundtrip_color_and_tags():
    stored = encode_annotation_content("重要洞见", color="yellow", tags=["ai", "rust", "ai"])
    assert stored.startswith("⟦meta:")
    meta = decode_annotation_content(stored)
    assert meta.body == "重要洞见"
    assert meta.color == "yellow"
    assert meta.tags == ("ai", "rust")


def test_plain_content_has_no_meta():
    meta = decode_annotation_content("just a note")
    assert meta.body == "just a note"
    assert meta.color is None
    assert meta.tags == ()


def test_normalize_color_rejects_unknown():
    try:
        normalize_color("neon")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unsupported color" in str(exc)

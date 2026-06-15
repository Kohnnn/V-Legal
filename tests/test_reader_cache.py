"""Tests for reader-layer caching (Phase 2)."""

from __future__ import annotations

from vlegal_prototype.structure import extract_sections, prepare_document_markup
from vlegal_prototype.citations import build_runtime_citation_support

SAMPLE = """# Luật mẫu

Căn cứ Hiến pháp;

Điều 1. Phạm vi điều chỉnh
Luật này quy định về thử nghiệm.

Điều 2. Đối tượng áp dụng
Áp dụng cho mọi tổ chức.
"""


def test_extract_sections_returns_independent_copies():
    first = extract_sections(SAMPLE)
    second = extract_sections(SAMPLE)
    # Same content, but distinct list/dict objects so callers can mutate safely.
    assert first == second
    assert first is not second
    assert first[0] is not second[0]
    # Mutating one copy must not affect the cached parse seen by the next call.
    first[0]["label"] = "MUTATED"
    third = extract_sections(SAMPLE)
    assert third[0]["label"] != "MUTATED"


def test_extract_sections_finds_articles():
    sections = extract_sections(SAMPLE)
    labels = [section["label"] for section in sections]
    assert any("Điều 1" in label for label in labels)
    assert any("Điều 2" in label for label in labels)


def test_outline_carries_depth_and_type():
    nested = """# Luật mẫu

## Phần thứ nhất

### Chương I

Điều 1. Phạm vi
Nội dung điều 1.
"""
    _, outline = prepare_document_markup(nested)
    by_type = {item["section_type"]: item["depth"] for item in outline}
    assert by_type.get("part") == 1
    assert by_type.get("chapter") == 2
    assert by_type.get("article") == 4
    assert all("depth" in item and "section_type" in item for item in outline)


def test_runtime_citation_support_returns_independent_copies(seeded_connection):
    doc = dict(
        seeded_connection.execute(
            "SELECT * FROM documents WHERE document_number = '22/2012/QH13'"
        ).fetchone()
    )
    first = build_runtime_citation_support(seeded_connection, doc)
    second = build_runtime_citation_support(seeded_connection, doc)
    assert first == second
    # Mutating one result must not corrupt the cached structure.
    first["citation_map"]["bogus"] = 999
    third = build_runtime_citation_support(seeded_connection, doc)
    assert "bogus" not in third["citation_map"]
    assert set(first.keys()) == {"citation_map", "section_counts", "section_labels"}

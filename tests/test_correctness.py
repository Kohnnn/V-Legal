"""Tests for Phase 3 correctness fixes."""

from __future__ import annotations

import sqlite3

import pytest

from vlegal_prototype.db import (
    InternalIdCollisionError,
    import_documents,
)
from vlegal_prototype.doc_number import (
    CONTEXTUAL_DOC_REFERENCE_PATTERN,
    CONTEXTUAL_DOC_REFERENCE_PATTERN_UNICODE,
    DOC_NUMBER_PATTERN,
    DOC_NUMBER_PATTERN_UNICODE,
)
from vlegal_prototype.relations import choose_target_document

from conftest import _make_record


def test_internal_id_collision_guard_within_batch(memory_connection):
    a = _make_record(
        internal_id=500,
        canonical_id="vn-issued-hf-aaa",
        document_number="10/2020/QH14",
        title="Doc A",
        content="noi dung a",
    )
    b = _make_record(
        internal_id=500,  # same internal id, different canonical id
        canonical_id="vn-issued-hf-bbb",
        document_number="11/2020/QH14",
        title="Doc B",
        content="noi dung b",
    )
    with pytest.raises(InternalIdCollisionError):
        import_documents(memory_connection, [a, b])


def test_internal_id_collision_guard_against_db(seeded_connection):
    # internal_id 101 already stored under vn-issued-hf-101.
    clashing = _make_record(
        internal_id=101,
        canonical_id="vn-issued-hf-DIFFERENT",
        document_number="99/2099/QH99",
        title="Clashing",
        content="noi dung",
    )
    with pytest.raises(InternalIdCollisionError):
        import_documents(seeded_connection, [clashing])


def test_reimport_same_canonical_id_is_allowed(seeded_connection):
    # Re-importing the same document (same internal id + canonical id) must work.
    same = _make_record(
        internal_id=101,
        canonical_id="vn-issued-hf-101",
        document_number="22/2012/QH13",
        title="Luật giá (updated)",
        content="noi dung moi",
    )
    result = import_documents(seeded_connection, [same])
    assert result["imported_count"] == 1


def test_doc_number_patterns_match_equivalent_text():
    ascii_text = "can cu luat so 22/2012/qh13 ngay"
    unicode_text = "căn cứ Luật số 22/2012/QH13 ngày"
    ascii_hit = CONTEXTUAL_DOC_REFERENCE_PATTERN.search(ascii_text)
    unicode_hit = CONTEXTUAL_DOC_REFERENCE_PATTERN_UNICODE.search(unicode_text)
    assert ascii_hit is not None
    assert unicode_hit is not None
    # ASCII pattern captures (type, number); unicode pattern captures (number).
    assert ascii_hit.group(2).upper().replace("-", "/") == "22/2012/QH13"
    assert unicode_hit.group(1).upper().replace("-", "/") == "22/2012/QH13"


def test_standalone_patterns_have_consistent_digit_bounds():
    # Both standalone variants cap the leading numeric block at 4 digits.
    long_number = "123456/2020/QH14"
    ascii_hit = DOC_NUMBER_PATTERN.search(long_number)
    unicode_hit = DOC_NUMBER_PATTERN_UNICODE.search(long_number)
    # Neither should match the full 6-digit leading block as a document number.
    assert ascii_hit is None or not ascii_hit.group(1).startswith("123456")
    assert unicode_hit is None or not unicode_hit.group(1).startswith("123456")


def test_choose_target_returns_confidence_tuple():
    source = {"id": 1, "title": "Source", "issuing_authority": "Quốc hội"}
    index = {
        "22/2012/qh13": [
            {
                "id": 2,
                "document_number": "22/2012/QH13",
                "legal_type": "Luật",
                "issuing_authority": "Quốc hội",
                "title": "Target",
                "year": 2012,
            }
        ]
    }
    target, confidence = choose_target_document(
        source,
        "22/2012/QH13",
        index,
        return_confidence=True,
    )
    assert target is not None
    assert confidence in {"high", "medium", "low"}

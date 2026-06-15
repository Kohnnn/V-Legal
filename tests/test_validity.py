"""Tests for legal validity status and text-provenance notices (Phases A & B)."""

from __future__ import annotations

from vlegal_prototype.search import search_documents
from vlegal_prototype.validity import (
    build_text_provenance_notice,
    build_validity_badge,
)

from conftest import _make_record


def _record_with(**overrides):
    base = dict(
        internal_id=overrides.pop("internal_id", 700),
        canonical_id=overrides.pop("canonical_id", "vn-issued-hf-700"),
        document_number=overrides.pop("document_number", "70/2020/QH14"),
        title=overrides.pop("title", "Doc"),
        content=overrides.pop("content", "noi dung"),
    )
    record = _make_record(**base)
    record.update(overrides)
    return record


def test_validity_badge_in_force_explicit():
    badge = build_validity_badge(
        {"status": "in_force", "source_system": "vbpl", "effective_date": "2020-07-01"}
    )
    assert badge["key"] == "in_force"
    assert badge["is_explicit"] is True
    assert badge["unverified"] is False
    assert badge["effective_date"] == "2020-07-01"


def test_validity_badge_unknown_for_bootstrap():
    badge = build_validity_badge({"status": "unknown", "source_system": "hf_bootstrap"})
    assert badge["key"] == "unknown"
    assert badge["is_explicit"] is False
    assert badge["unverified"] is True


def test_validity_badge_partial_and_expired():
    assert build_validity_badge({"status": "partially_expired"})["key"] == "partial"
    assert build_validity_badge({"status": "repealed"})["key"] == "expired"


def test_text_provenance_notice_for_ocr():
    notice = build_text_provenance_notice(
        {"text_source": "ocr", "parse_confidence": "low", "url": "https://example.gov.vn"}
    )
    assert notice is not None
    assert notice["severity"] == "high"
    assert notice["verify_url"] == "https://example.gov.vn"
    assert notice["reasons"]


def test_text_provenance_notice_absent_for_clean_html():
    notice = build_text_provenance_notice(
        {"text_source": "html", "parse_confidence": "high"}
    )
    assert notice is None


def test_status_filter_narrows_results(memory_connection):
    from vlegal_prototype.db import import_documents

    in_force = _record_with(
        internal_id=801,
        canonical_id="vn-issued-hf-801",
        document_number="81/2020/QH14",
        title="Luật còn hiệu lực",
        content="quy dinh hien hanh",
        status="in_force",
    )
    expired = _record_with(
        internal_id=802,
        canonical_id="vn-issued-hf-802",
        document_number="82/2000/QH10",
        title="Luật hết hiệu lực",
        content="quy dinh cu",
        status="expired",
    )
    import_documents(memory_connection, [in_force, expired])

    result = search_documents(
        connection=memory_connection,
        query="",
        page=1,
        page_size=10,
        status="in_force",
    )
    statuses = {item.get("status") for item in result["items"]}
    assert statuses == {"in_force"}


def test_status_column_persisted_on_import(memory_connection):
    from vlegal_prototype.db import import_documents

    record = _record_with(
        internal_id=900,
        canonical_id="vn-issued-hf-900",
        document_number="90/2021/QH15",
        title="Doc status",
        content="noi dung",
        status="in_force",
        effective_date="2021-01-01",
        expiry_date="",
    )
    import_documents(memory_connection, [record])
    row = memory_connection.execute(
        "SELECT status, effective_date, expiry_date FROM documents WHERE id = 900"
    ).fetchone()
    assert row["status"] == "in_force"
    assert row["effective_date"] == "2021-01-01"

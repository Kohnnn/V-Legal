"""Tests for search index normalization and recency ordering (Phase 1)."""

from __future__ import annotations

from vlegal_prototype.db import normalize_document_number
from vlegal_prototype.search import get_recent_documents, search_documents


def test_normalize_document_number():
    assert normalize_document_number("22/2012/QH13") == "22/2012/QH13"
    assert normalize_document_number(" 22/2012/qh13 ") == "22/2012/QH13"
    assert normalize_document_number("01-SL") == "01/SL"
    assert normalize_document_number("") == ""
    assert normalize_document_number(None) == ""


def test_document_number_norm_is_populated(seeded_connection):
    rows = seeded_connection.execute(
        "SELECT document_number, document_number_norm FROM documents"
    ).fetchall()
    by_number = {row["document_number"]: row["document_number_norm"] for row in rows}
    assert by_number["22/2012/QH13"] == "22/2012/QH13"
    assert by_number["01-SL"] == "01/SL"


def test_identifier_search_uses_normalized_index(seeded_connection):
    # Lowercased + dash form should still resolve via the normalized column.
    result = search_documents(
        connection=seeded_connection,
        query="01-sl",
        page=1,
        page_size=10,
    )
    assert result["total"] >= 1
    assert any(item["document_number"] == "01-SL" for item in result["items"])


def test_recent_documents_orders_by_recency_not_hash(seeded_connection):
    rows = get_recent_documents(seeded_connection, limit=10)
    # All seeded docs share the same imported_at second, so the secondary
    # year-desc ordering should surface the 2012 doc ahead of the 1945 one.
    years_by_number = {
        "22/2012/QH13": 2012,
        "55/2010/QH12": 2010,
        "01-SL": 1945,
    }
    ordered_years = [years_by_number.get(row["document_number"]) for row in rows]
    ordered_years = [year for year in ordered_years if year is not None]
    assert ordered_years == sorted(ordered_years, reverse=True)

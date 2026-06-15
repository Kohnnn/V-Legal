"""Tests for the lighter metadata-only document projection (Phase E)."""

from __future__ import annotations

from vlegal_prototype.search import get_document, get_document_meta


def test_get_document_meta_excludes_body_columns(seeded_connection):
    meta = get_document_meta(seeded_connection, 101)
    assert meta is not None
    # Body blobs must not be loaded by the lighter projection.
    assert "content" not in meta
    assert "plain_content" not in meta
    # But metadata fields the compare/preview paths need are present.
    for field in ("id", "title", "document_number", "legal_type", "status"):
        assert field in meta


def test_get_document_meta_matches_full_metadata(seeded_connection):
    full = get_document(seeded_connection, 101)
    meta = get_document_meta(seeded_connection, 101)
    for field in ("id", "title", "document_number", "legal_type", "issuance_date"):
        assert meta[field] == full[field]


def test_get_document_meta_missing_returns_none(seeded_connection):
    assert get_document_meta(seeded_connection, 999999) is None

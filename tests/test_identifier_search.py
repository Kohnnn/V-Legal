"""Regression tests for document-number (identifier-first) search.

Searching by document number is the most common legal lookup. A missing
``datetime`` import in ``search.py`` previously caused this path to raise
``NameError`` whenever an identifier query had matches.
"""

from __future__ import annotations

from vlegal_prototype.search import (
    looks_like_identifier_query,
    search_documents,
)


def test_identifier_query_detection():
    assert looks_like_identifier_query("22/2012/QH13") is True
    assert looks_like_identifier_query("an toàn thực phẩm") is False


def test_search_by_document_number_does_not_raise(seeded_connection):
    # This is the regression: a matching identifier query must not raise.
    result = search_documents(
        connection=seeded_connection,
        query="22/2012/QH13",
        page=1,
        page_size=10,
    )
    assert result["total"] >= 1
    numbers = {item["document_number"] for item in result["items"]}
    assert "22/2012/QH13" in numbers


def test_search_by_document_number_with_dash_normalizes(seeded_connection):
    # "01-SL" should normalize to match "01-SL" stored form.
    result = search_documents(
        connection=seeded_connection,
        query="01-SL",
        page=1,
        page_size=10,
    )
    assert result["total"] >= 1
    numbers = {item["document_number"] for item in result["items"]}
    assert "01-SL" in numbers


def test_concept_search_still_works(seeded_connection):
    result = search_documents(
        connection=seeded_connection,
        query="an toàn thực phẩm",
        page=1,
        page_size=10,
    )
    assert result["total"] >= 1
    titles = {item["title"] for item in result["items"]}
    assert any("an toàn thực phẩm" in title.lower() for title in titles)

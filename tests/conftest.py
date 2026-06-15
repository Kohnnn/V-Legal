"""Shared pytest fixtures for V-Legal tests.

Tests build a tiny temporary SQLite corpus from scratch via the real schema and
import path. They never depend on the large workspace database under
``data/corpus/sqlite/vlegal.sqlite``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from vlegal_prototype.db import import_documents, initialize_database


def _make_record(
    *,
    internal_id: int,
    canonical_id: str,
    document_number: str,
    title: str,
    content: str,
    legal_type: str = "Luật",
    issuing_authority: str = "Quốc hội",
    issuance_date: str = "2012-06-20",
    year: int | None = 2012,
    source_system: str = "hf_bootstrap",
) -> dict:
    plain_content = content.lower()
    return {
        "id": internal_id,
        "canonical_id": canonical_id,
        "document_number": document_number,
        "title": title,
        "url": "",
        "legal_type": legal_type,
        "legal_sectors": "",
        "issuing_authority": issuing_authority,
        "issuance_date": issuance_date,
        "signers": "",
        "content": content,
        "plain_content": plain_content,
        "excerpt": plain_content[:160],
        "year": year,
        "source": "markdown_corpus",
        "source_system": source_system,
        "source_document_id": canonical_id,
        "document_layer": "issued",
        "text_source": "html",
        "parse_confidence": "high",
        "corpus_path": f"issued/{canonical_id}.md",
        "passages": [
            {"ordinal": 0, "heading": "Mở đầu", "text": title},
            {"ordinal": 1, "heading": "Điều 1", "text": content},
        ],
    }


SAMPLE_RECORDS = [
    _make_record(
        internal_id=101,
        canonical_id="vn-issued-hf-101",
        document_number="22/2012/QH13",
        title="Luật giá",
        content="Luật này quy định về quản lý giá hàng hóa và dịch vụ.",
    ),
    _make_record(
        internal_id=102,
        canonical_id="vn-issued-hf-102",
        document_number="55/2010/QH12",
        title="Luật an toàn thực phẩm",
        content="Luật này quy định về an toàn thực phẩm trong sản xuất.",
        issuance_date="2010-06-17",
        year=2010,
    ),
    _make_record(
        internal_id=103,
        canonical_id="vn-issued-hf-103",
        document_number="01-SL",
        title="Sắc lệnh số 01 về tổ chức",
        content="Sắc lệnh này quy định về tổ chức bộ máy nhà nước.",
        legal_type="Sắc lệnh",
        issuance_date="1945-09-10",
        year=1945,
    ),
]


@pytest.fixture()
def memory_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_database(connection)
    yield connection
    connection.close()


@pytest.fixture()
def seeded_connection(memory_connection: sqlite3.Connection) -> sqlite3.Connection:
    import_documents(memory_connection, SAMPLE_RECORDS)
    return memory_connection

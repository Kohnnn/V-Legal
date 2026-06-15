"""Tests for body-level repeal/amend extraction (Phase D)."""

from __future__ import annotations

from vlegal_prototype.db import import_documents
from vlegal_prototype.relations import (
    get_document_relation_graph,
    rebuild_relationship_graph,
)

from conftest import _make_record


def test_body_endmatter_repeal_creates_relation(memory_connection):
    # Target document that will be repealed.
    target = _make_record(
        internal_id=1001,
        canonical_id="vn-issued-hf-1001",
        document_number="10/2005/QH11",
        title="Luật cũ",
        content="Luật này quy định nội dung cũ.",
        year=2005,
    )
    # Newer document whose TITLE does NOT mention the repeal, but whose body
    # endmatter does (the common "điều khoản thi hành" pattern).
    newer = _make_record(
        internal_id=1002,
        canonical_id="vn-issued-hf-1002",
        document_number="20/2015/QH13",
        title="Luật mới về cùng lĩnh vực",
        content=(
            "Điều 1. Phạm vi điều chỉnh\n"
            "Luật này quy định nội dung mới.\n\n"
            "Điều 50. Điều khoản thi hành\n"
            "Luật số 10/2005/QH11 hết hiệu lực kể từ ngày Luật này có hiệu lực. "
            "Bãi bỏ Luật số 10/2005/QH11."
        ),
        year=2015,
    )
    import_documents(memory_connection, [target, newer])
    rebuild_relationship_graph(memory_connection)

    graph = get_document_relation_graph(memory_connection, 1002)
    outgoing_targets = [
        item["id"]
        for group in graph.get("outgoing", [])
        for item in group["items"]
    ]
    assert 1001 in outgoing_targets

    # The relation should record body evidence (not the title).
    row = memory_connection.execute(
        """
        SELECT evidence_text, confidence
        FROM document_relations
        WHERE source_document_id = 1002 AND target_document_id = 1001
        """
    ).fetchone()
    assert row is not None
    assert "thân văn bản" in row["evidence_text"]
    # Body evidence is downgraded relative to title evidence.
    assert row["confidence"] in {"medium", "low"}

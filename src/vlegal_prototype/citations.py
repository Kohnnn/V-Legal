from __future__ import annotations

import re
import sqlite3

from .relations import (
    DOC_NUMBER_PATTERN,
    choose_target_document,
    normalize_document_number,
)
from .structure import extract_sections
from .taxonomy import normalize_ascii


CITATION_LABELS = {
    "amends": "Amends",
    "replaces": "Replaces",
    "guides": "Guides",
    "basis_for": "Legal basis",
    "implements": "Implements",
    "cites": "Cites",
}

INVERSE_CITATION_LABELS = {
    "amends": "Amended by",
    "replaces": "Replaced by",
    "guides": "Guided by",
    "basis_for": "Used as legal basis by",
    "implements": "Implemented by",
    "cites": "Cited by",
}

CITATION_ORDER = (
    "amends",
    "replaces",
    "guides",
    "implements",
    "basis_for",
    "cites",
)

ARTICLE_REFERENCE_PATTERN = re.compile(r"\bdieu\s+\d+[a-z]?\b", re.IGNORECASE)

LINK_TYPE_PATTERNS = (
    (
        "replaces",
        (
            re.compile(r"\bbai bo(?: toan bo)?\b"),
            re.compile(r"\bthay the\b"),
            re.compile(r"\bhuy bo\b"),
        ),
    ),
    (
        "amends",
        (
            re.compile(r"\bsua doi(?:, bo sung)?\b"),
            re.compile(r"\bbo sung(?: mot so dieu)?\b"),
            re.compile(r"\bdinh chinh\b"),
        ),
    ),
    (
        "guides",
        (
            re.compile(r"\bhuong dan(?: thi hanh| thuc hien)?\b"),
            re.compile(r"\bquy dinh chi tiet\b"),
        ),
    ),
    (
        "implements",
        (
            re.compile(r"\btrien khai thuc hien\b"),
            re.compile(r"\bthi hanh\b"),
        ),
    ),
    (
        "basis_for",
        (
            re.compile(r"\bcan cu\b"),
            re.compile(r"\btheo quy dinh tai\b"),
        ),
    ),
)


def infer_link_type(window_text: str) -> tuple[str, str | None]:
    for link_type, patterns in LINK_TYPE_PATTERNS:
        for pattern in patterns:
            match = pattern.search(window_text)
            if match:
                return link_type, match.group(0)
    return "cites", None


def extract_section_mentions(section: dict, source_document: dict) -> list[dict]:
    normalized_text = normalize_ascii(section["text"])
    source_number = normalize_document_number(
        source_document.get("document_number") or ""
    )
    mentions: list[dict] = []
    seen: set[tuple[str, str]] = set()
    mention_order = 1

    for match in DOC_NUMBER_PATTERN.finditer(normalized_text):
        referenced_number = normalize_document_number(match.group(0))
        if not referenced_number or referenced_number == source_number:
            continue

        window_before = normalized_text[max(0, match.start() - 120) : match.start()]
        link_type, cue_phrase = infer_link_type(window_before)
        key = (referenced_number, link_type)
        if key in seen:
            continue

        article_match = ARTICLE_REFERENCE_PATTERN.search(window_before)
        mentions.append(
            {
                "mention_order": mention_order,
                "raw_reference": match.group(0),
                "referenced_number": referenced_number,
                "referenced_label": article_match.group(0) if article_match else None,
                "cue_phrase": cue_phrase,
                "mention_type": "document",
                "link_type": link_type,
                "confidence": "high" if cue_phrase else "medium",
            }
        )
        seen.add(key)
        mention_order += 1

    return mentions


def get_citation_count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM citation_links").fetchone()[0]


def rebuild_citation_index(connection: sqlite3.Connection) -> int:
    documents = [
        dict(row)
        for row in connection.execute(
            """
            SELECT id, document_number, title, content, issuing_authority, year
            FROM documents
            ORDER BY id ASC
            """
        ).fetchall()
    ]

    from .relations import build_document_number_index

    number_index = build_document_number_index(connection)
    link_count = 0

    with connection:
        connection.execute("DELETE FROM citation_links")
        connection.execute("DELETE FROM citation_mentions")
        connection.execute("DELETE FROM document_sections")

        section_sql = """
        INSERT INTO document_sections (document_id, ordinal, section_type, label, anchor, text)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        mention_sql = """
        INSERT INTO citation_mentions (
            source_document_id,
            source_section_id,
            mention_order,
            raw_reference,
            referenced_number,
            referenced_label,
            cue_phrase,
            mention_type,
            confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        link_sql = """
        INSERT OR IGNORE INTO citation_links (
            mention_id,
            target_document_id,
            target_section_id,
            link_type,
            score,
            match_method
        ) VALUES (?, ?, ?, ?, ?, ?)
        """

        for document in documents:
            section_records = extract_sections(document["content"])
            if section_records:
                section_records[0] = {**section_records[0], "text": document["title"]}

            for section in section_records:
                cursor = connection.execute(
                    section_sql,
                    (
                        document["id"],
                        section["ordinal"],
                        section["section_type"],
                        section["label"],
                        section["anchor"],
                        section["text"],
                    ),
                )
                section_id = cursor.lastrowid
                for mention in extract_section_mentions(section, document):
                    mention_cursor = connection.execute(
                        mention_sql,
                        (
                            document["id"],
                            section_id,
                            mention["mention_order"],
                            mention["raw_reference"],
                            mention["referenced_number"],
                            mention["referenced_label"],
                            mention["cue_phrase"],
                            mention["mention_type"],
                            mention["confidence"],
                        ),
                    )
                    target_document = choose_target_document(
                        document, mention["referenced_number"], number_index
                    )
                    if not target_document:
                        continue
                    connection.execute(
                        link_sql,
                        (
                            mention_cursor.lastrowid,
                            target_document["id"],
                            None,
                            mention["link_type"],
                            1.0,
                            "document_number",
                        ),
                    )
                    link_count += 1

    return link_count


def get_section_citation_counts(
    connection: sqlite3.Connection, document_id: int
) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT s.anchor, COUNT(cl.target_document_id) AS total
        FROM document_sections s
        LEFT JOIN citation_mentions m ON m.source_section_id = s.id
        LEFT JOIN citation_links cl ON cl.mention_id = m.id
        WHERE s.document_id = ?
        GROUP BY s.anchor
        """,
        (document_id,),
    ).fetchall()
    return {row["anchor"]: row["total"] for row in rows}


def _group_citation_rows(rows: list[sqlite3.Row], direction: str) -> list[dict]:
    label_map = CITATION_LABELS if direction == "outgoing" else INVERSE_CITATION_LABELS
    grouped_by_type: dict[str, dict[int, dict]] = {
        link_type: {} for link_type in CITATION_ORDER
    }

    for row in rows:
        target_id = row["linked_document_id"]
        link_type = row["link_type"]
        if target_id not in grouped_by_type[link_type]:
            grouped_by_type[link_type][target_id] = {
                "id": row["linked_document_id"],
                "title": row["linked_title"],
                "document_number": row["linked_document_number"],
                "legal_type": row["linked_legal_type"],
                "issuance_date": row["linked_issuance_date"],
                "sections": [],
                "count": 0,
            }
        item = grouped_by_type[link_type][target_id]
        item["count"] += 1
        section_ref = {
            "label": row["source_section_label"],
            "anchor": row["source_section_anchor"],
        }
        if section_ref not in item["sections"]:
            item["sections"].append(section_ref)

    groups: list[dict] = []
    for link_type in CITATION_ORDER:
        items = list(grouped_by_type[link_type].values())
        if not items:
            continue
        items.sort(
            key=lambda item: (
                -item["count"],
                item["issuance_date"] or "",
                item["title"],
            )
        )
        groups.append(
            {
                "key": link_type
                if direction == "outgoing"
                else f"{link_type}_incoming",
                "label": label_map[link_type],
                "items": items,
            }
        )
    return groups


def get_document_citation_graph(
    connection: sqlite3.Connection, document_id: int
) -> dict:
    outgoing_rows = connection.execute(
        """
        SELECT
            cl.link_type,
            d.id AS linked_document_id,
            d.title AS linked_title,
            d.document_number AS linked_document_number,
            d.legal_type AS linked_legal_type,
            d.issuance_date AS linked_issuance_date,
            s.label AS source_section_label,
            s.anchor AS source_section_anchor
        FROM citation_links cl
        JOIN citation_mentions m ON m.id = cl.mention_id
        JOIN document_sections s ON s.id = m.source_section_id
        JOIN documents d ON d.id = cl.target_document_id
        WHERE m.source_document_id = ?
        ORDER BY d.year DESC, d.title ASC, s.ordinal ASC
        """,
        (document_id,),
    ).fetchall()

    incoming_rows = connection.execute(
        """
        SELECT
            cl.link_type,
            d.id AS linked_document_id,
            d.title AS linked_title,
            d.document_number AS linked_document_number,
            d.legal_type AS linked_legal_type,
            d.issuance_date AS linked_issuance_date,
            s.label AS source_section_label,
            s.anchor AS source_section_anchor
        FROM citation_links cl
        JOIN citation_mentions m ON m.id = cl.mention_id
        JOIN document_sections s ON s.id = m.source_section_id
        JOIN documents d ON d.id = m.source_document_id
        WHERE cl.target_document_id = ?
        ORDER BY d.year DESC, d.title ASC, s.ordinal ASC
        """,
        (document_id,),
    ).fetchall()

    return {
        "outgoing_groups": _group_citation_rows(list(outgoing_rows), "outgoing"),
        "incoming_groups": _group_citation_rows(list(incoming_rows), "incoming"),
        "outgoing_total": len(outgoing_rows),
        "incoming_total": len(incoming_rows),
    }

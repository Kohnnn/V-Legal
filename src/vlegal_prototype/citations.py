from __future__ import annotations

import re
import sqlite3

from .relations import (
    choose_target_document,
    get_document_relation_graph,
    iter_document_reference_matches,
    normalize_document_number,
    resolve_target_document,
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
ARTICLE_REFERENCE_CAPTURE_PATTERN = re.compile(r"\bdieu\s+(\d+[a-z]?)\b", re.IGNORECASE)
CLAUSE_REFERENCE_PATTERN = re.compile(r"\bkhoan\s+(\d+[a-z]?)\b", re.IGNORECASE)
POINT_REFERENCE_PATTERN = re.compile(r"\bdiem\s+([a-z])\b", re.IGNORECASE)
REFERENCE_DATE_PATTERN = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-](\d{2,4})\b")


def normalize_section_label(value: str | None) -> str:
    normalized = normalize_ascii(value or "")
    normalized = re.sub(r"[^0-9a-z\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def summarize_excerpt(value: str | None, max_length: int = 220) -> str:
    collapsed = " ".join((value or "").split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3].rstrip() + "..."


def extract_article_component(value: str | None) -> str | None:
    normalized = normalize_ascii(value or "")
    match = ARTICLE_REFERENCE_CAPTURE_PATTERN.search(normalized)
    if not match:
        return None
    return f"Điều {match.group(1)}"


def extract_reference_label(window_text: str) -> str | None:
    normalized = normalize_ascii(window_text)
    article_match = None
    for match in ARTICLE_REFERENCE_CAPTURE_PATTERN.finditer(normalized):
        article_match = match
    if not article_match:
        return None

    clause_match = None
    for match in CLAUSE_REFERENCE_PATTERN.finditer(normalized):
        if match.start() <= article_match.end():
            clause_match = match

    point_match = None
    for match in POINT_REFERENCE_PATTERN.finditer(normalized):
        if match.start() <= article_match.end():
            point_match = match

    label_parts: list[str] = []
    if point_match:
        label_parts.append(f"Điểm {point_match.group(1).lower()}")
    if clause_match:
        label_parts.append(f"Khoản {clause_match.group(1)}")
    label_parts.append(f"Điều {article_match.group(1)}")
    return " ".join(label_parts)


def extract_reference_year(window_text: str) -> int | None:
    max_year = 2100
    for match in REFERENCE_DATE_PATTERN.finditer(window_text):
        year_token = match.group(1)
        year = int(year_token)
        if len(year_token) == 2:
            year += 1900 if year >= 40 else 2000
        if 1800 <= year <= max_year:
            return year
    return None


def extract_reference_quote(
    text: str | None, raw_reference: str | None, *, window: int = 140
) -> str:
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return ""
    if raw_reference:
        match = re.search(re.escape(raw_reference), collapsed, re.IGNORECASE)
        if match:
            start = max(0, match.start() - window)
            end = min(len(collapsed), match.end() + window)
            snippet = collapsed[start:end].strip()
            if start > 0:
                snippet = f"... {snippet}"
            if end < len(collapsed):
                snippet = f"{snippet} ..."
            return snippet
    return summarize_excerpt(collapsed, max_length=min(window * 2, 260))


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
    seen: set[tuple[str, str, str, str, str]] = set()
    mention_order = 1

    for match in iter_document_reference_matches(normalized_text):
        referenced_number = match["referenced_number"]
        if not referenced_number or referenced_number == source_number:
            continue

        window_before = normalized_text[max(0, match["start"] - 180) : match["start"]]
        window_after = normalized_text[match["end"] : match["end"] + 140]
        reference_window = f"{window_before} {window_after}".strip()
        link_type, cue_phrase = infer_link_type(window_before)
        referenced_label = extract_reference_label(reference_window)
        reference_year = extract_reference_year(window_after) or extract_reference_year(
            reference_window
        )
        legal_type_hint = match.get("legal_type_hint") or ""
        key = (
            referenced_number,
            link_type,
            referenced_label or "",
            legal_type_hint,
            str(reference_year or ""),
        )
        if key in seen:
            continue

        mentions.append(
            {
                "mention_order": mention_order,
                "raw_reference": match["raw_reference"],
                "referenced_number": referenced_number,
                "referenced_label": referenced_label,
                "cue_phrase": cue_phrase,
                "mention_type": "document",
                "link_type": link_type,
                "legal_type_hint": match.get("legal_type_hint"),
                "reference_year": reference_year,
                "reference_context": reference_window,
                "confidence": "high" if cue_phrase or referenced_label else "medium",
            }
        )
        seen.add(key)
        mention_order += 1

    return mentions


def get_citation_count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM citation_links").fetchone()[0]


def load_target_sections(
    connection: sqlite3.Connection,
    target_document_id: int,
    section_cache: dict[int, list[dict]],
) -> list[dict]:
    if target_document_id in section_cache:
        return section_cache[target_document_id]

    rows = connection.execute(
        """
        SELECT id, label, anchor, text
        FROM document_sections
        WHERE document_id = ?
        ORDER BY ordinal ASC
        """,
        (target_document_id,),
    ).fetchall()
    section_cache[target_document_id] = [
        {
            "id": row["id"],
            "label": row["label"],
            "anchor": row["anchor"],
            "text": row["text"],
            "normalized_label": normalize_section_label(row["label"]),
            "article_component": normalize_section_label(
                extract_article_component(row["label"]) or ""
            ),
        }
        for row in rows
    ]
    return section_cache[target_document_id]


def resolve_target_section_id(
    connection: sqlite3.Connection,
    *,
    target_document_id: int,
    referenced_label: str | None,
    section_cache: dict[int, list[dict]],
) -> int | None:
    normalized_reference = normalize_section_label(referenced_label)
    if not normalized_reference:
        return None

    sections = load_target_sections(connection, target_document_id, section_cache)
    if not sections:
        return None

    for section in sections:
        if section["normalized_label"] == normalized_reference:
            return section["id"]

    article_reference = normalize_section_label(
        extract_article_component(referenced_label) or ""
    )
    if article_reference:
        for section in sections:
            if section["article_component"] == article_reference:
                return section["id"]

    for section in sections:
        if (
            normalized_reference in section["normalized_label"]
            or section["normalized_label"] in normalized_reference
        ):
            return section["id"]

    return None


def rebuild_citation_index(connection: sqlite3.Connection) -> int:
    from .relations import build_document_number_index

    number_index = build_document_number_index(connection)
    link_count = 0
    section_cache: dict[int, list[dict]] = {}

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

        document_cursor = connection.execute(
            """
            SELECT id, document_number, title, content, issuing_authority, year
            FROM documents
            ORDER BY id ASC
            """
        )
        for row in document_cursor:
            document = dict(row)
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
                _ = cursor.lastrowid

        document_cursor = connection.execute(
            """
            SELECT id, document_number, title, issuing_authority, year
            FROM documents
            ORDER BY id ASC
            """
        )
        for row in document_cursor:
            document = dict(row)
            section_rows = [
                dict(section_row)
                for section_row in connection.execute(
                    """
                    SELECT id, label, anchor, text
                    FROM document_sections
                    WHERE document_id = ?
                    ORDER BY ordinal ASC
                    """,
                    (document["id"],),
                ).fetchall()
            ]

            for section in section_rows:
                for mention in extract_section_mentions(section, document):
                    mention_cursor = connection.execute(
                        mention_sql,
                        (
                            document["id"],
                            section["id"],
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
                        document,
                        mention["referenced_number"],
                        number_index,
                        reference_legal_type=mention.get("legal_type_hint"),
                        reference_year=mention.get("reference_year"),
                        reference_context_text=mention.get("reference_context"),
                    )
                    if not target_document:
                        continue
                    target_section_id = resolve_target_section_id(
                        connection,
                        target_document_id=target_document["id"],
                        referenced_label=mention["referenced_label"],
                        section_cache=section_cache,
                    )
                    connection.execute(
                        link_sql,
                        (
                            mention_cursor.lastrowid,
                            target_document["id"],
                            target_section_id,
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


def needs_runtime_citation_resolution(mention: dict) -> bool:
    referenced_number = mention.get("referenced_number") or ""
    return bool(mention.get("legal_type_hint")) or "/" not in referenced_number


def build_runtime_citation_support(
    connection: sqlite3.Connection, document: dict
) -> dict:
    citation_map: dict[str, int] = {}
    section_counts: dict[str, int] = {}
    section_labels: dict[str, int] = {}

    for section in extract_sections(document["content"]):
        if not section.get("text"):
            continue
        section_total = 0
        for mention in extract_section_mentions(section, document):
            if not needs_runtime_citation_resolution(mention):
                continue
            target_document = resolve_target_document(
                connection,
                document,
                mention["referenced_number"],
                reference_legal_type=mention.get("legal_type_hint"),
                reference_year=mention.get("reference_year"),
                reference_context_text=mention.get("reference_context"),
            )
            if not target_document:
                continue
            citation_map.setdefault(
                normalize_document_number(mention["raw_reference"]),
                target_document["id"],
            )
            section_total += 1

        if section_total:
            section_counts[section["anchor"]] = section_total
            section_labels[section["label"]] = (
                section_labels.get(section["label"], 0) + section_total
            )

    return {
        "citation_map": citation_map,
        "section_counts": section_counts,
        "section_labels": section_labels,
    }


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


def resolve_target_section(
    connection: sqlite3.Connection,
    *,
    target_document_id: int,
    referenced_label: str | None,
    target_section_id: int | None = None,
) -> dict | None:
    if target_section_id:
        row = connection.execute(
            """
            SELECT id, label, anchor, text
            FROM document_sections
            WHERE id = ?
            """,
            (target_section_id,),
        ).fetchone()
        if row:
            return {
                "id": row["id"],
                "label": row["label"],
                "anchor": row["anchor"],
                "excerpt": summarize_excerpt(row["text"]),
            }

    normalized_reference = normalize_section_label(referenced_label)
    if not normalized_reference:
        return None

    article_reference = normalize_section_label(
        extract_article_component(referenced_label) or ""
    )

    rows = connection.execute(
        """
        SELECT id, label, anchor, text
        FROM document_sections
        WHERE document_id = ?
        ORDER BY ordinal ASC
        """,
        (target_document_id,),
    ).fetchall()
    if not rows:
        return None

    for row in rows:
        if normalize_section_label(row["label"]) == normalized_reference:
            return {
                "id": row["id"],
                "label": row["label"],
                "anchor": row["anchor"],
                "excerpt": summarize_excerpt(row["text"]),
            }

    if article_reference:
        for row in rows:
            if normalize_section_label(row["label"]) == article_reference:
                return {
                    "id": row["id"],
                    "label": row["label"],
                    "anchor": row["anchor"],
                    "excerpt": summarize_excerpt(row["text"]),
                }

    for row in rows:
        normalized_label = normalize_section_label(row["label"])
        if (
            normalized_reference in normalized_label
            or normalized_label in normalized_reference
        ):
            return {
                "id": row["id"],
                "label": row["label"],
                "anchor": row["anchor"],
                "excerpt": summarize_excerpt(row["text"]),
            }
    return None


def get_inline_citation_preview(
    connection: sqlite3.Connection,
    *,
    source_document_id: int,
    target_document_id: int,
    source_anchor: str | None = None,
    raw_reference: str | None = None,
) -> dict | None:
    rows = connection.execute(
        """
        SELECT
            m.id AS mention_id,
            m.raw_reference,
            m.referenced_number,
            m.referenced_label,
            m.cue_phrase,
            m.confidence,
            m.mention_order,
            cl.link_type,
            cl.target_section_id,
            s.id AS source_section_id,
            s.label AS source_section_label,
            s.anchor AS source_section_anchor,
            s.text AS source_section_text,
            d.id AS target_document_id,
            d.title AS target_title,
            d.document_number AS target_document_number,
            d.legal_type AS target_legal_type,
            d.issuing_authority AS target_issuing_authority,
            d.issuance_date AS target_issuance_date,
            d.excerpt AS target_excerpt
        FROM citation_links cl
        JOIN citation_mentions m ON m.id = cl.mention_id
        JOIN document_sections s ON s.id = m.source_section_id
        JOIN documents d ON d.id = cl.target_document_id
        WHERE m.source_document_id = ?
          AND cl.target_document_id = ?
        ORDER BY s.ordinal ASC, m.mention_order ASC
        """,
        (source_document_id, target_document_id),
    ).fetchall()
    if not rows:
        return None

    raw_reference_norm = normalize_document_number(raw_reference or "")
    best_row = None
    best_score = -1
    for row in rows:
        score = 0
        if source_anchor and row["source_section_anchor"] == source_anchor:
            score += 4
        if raw_reference and row["raw_reference"] == raw_reference:
            score += 3
        if raw_reference_norm and row["referenced_number"] == raw_reference_norm:
            score += 2
        if row["referenced_label"]:
            score += 1
        if score > best_score:
            best_score = score
            best_row = row

    row = best_row or rows[0]
    relation_graph = get_document_relation_graph(connection, target_document_id)
    citation_graph = get_document_citation_graph(connection, target_document_id)
    target_section = resolve_target_section(
        connection,
        target_document_id=target_document_id,
        referenced_label=row["referenced_label"],
        target_section_id=row["target_section_id"],
    )

    incoming_rows = connection.execute(
        """
        SELECT
            d.id,
            d.title,
            d.document_number,
            d.legal_type,
            d.issuance_date,
            s.label AS source_section_label,
            s.anchor AS source_section_anchor,
            cl.link_type
        FROM citation_links cl
        JOIN citation_mentions m ON m.id = cl.mention_id
        JOIN document_sections s ON s.id = m.source_section_id
        JOIN documents d ON d.id = m.source_document_id
        WHERE cl.target_document_id = ?
          AND m.source_document_id <> ?
        ORDER BY d.year DESC, d.title ASC, s.ordinal ASC
        LIMIT 3
        """,
        (target_document_id, source_document_id),
    ).fetchall()

    signals: list[dict] = []
    for group in relation_graph.get("incoming", []):
        if group.get("key") in {"replaces_incoming", "amends_incoming"} and group.get(
            "items"
        ):
            item = group["items"][0]
            signals.append(
                {
                    "kind": "updated-by",
                    "label": group["label"],
                    "document": {
                        "id": item["id"],
                        "title": item["title"],
                        "document_number": item.get("document_number"),
                    },
                }
            )
            break
    for group in relation_graph.get("outgoing", []):
        if group.get("key") in {"replaces", "amends"} and group.get("items"):
            item = group["items"][0]
            signals.append(
                {
                    "kind": "changes-older",
                    "label": group["label"],
                    "document": {
                        "id": item["id"],
                        "title": item["title"],
                        "document_number": item.get("document_number"),
                    },
                }
            )
            break
    if citation_graph.get("incoming_total"):
        top_group = citation_graph["incoming_groups"][0]
        top_item = top_group["items"][0]
        signals.append(
            {
                "kind": "mentioned-by",
                "label": top_group["label"],
                "count": citation_graph["incoming_total"],
                "document": {
                    "id": top_item["id"],
                    "title": top_item["title"],
                    "document_number": top_item.get("document_number"),
                },
            }
        )

    return {
        "source_section": {
            "id": row["source_section_id"],
            "label": row["source_section_label"],
            "anchor": row["source_section_anchor"],
            "excerpt": summarize_excerpt(row["source_section_text"], max_length=180),
            "quote": extract_reference_quote(
                row["source_section_text"], row["raw_reference"]
            ),
        },
        "mention": {
            "id": row["mention_id"],
            "raw_reference": row["raw_reference"],
            "referenced_number": row["referenced_number"],
            "referenced_label": row["referenced_label"],
            "cue_phrase": row["cue_phrase"],
            "confidence": row["confidence"],
            "link_type": row["link_type"],
            "link_label": CITATION_LABELS.get(
                row["link_type"], row["link_type"].title()
            ),
        },
        "target_document": {
            "id": row["target_document_id"],
            "title": row["target_title"],
            "document_number": row["target_document_number"],
            "legal_type": row["target_legal_type"],
            "issuing_authority": row["target_issuing_authority"],
            "issuance_date": row["target_issuance_date"],
            "excerpt": summarize_excerpt(row["target_excerpt"]),
        },
        "target_section": target_section,
        "incoming_mentions": [
            {
                "id": item["id"],
                "title": item["title"],
                "document_number": item["document_number"],
                "legal_type": item["legal_type"],
                "issuance_date": item["issuance_date"],
                "source_section_label": item["source_section_label"],
                "source_section_anchor": item["source_section_anchor"],
                "link_type": item["link_type"],
                "link_label": INVERSE_CITATION_LABELS.get(
                    item["link_type"], item["link_type"].title()
                ),
            }
            for item in incoming_rows
        ],
        "incoming_total": citation_graph.get("incoming_total", 0),
        "signals": signals,
    }

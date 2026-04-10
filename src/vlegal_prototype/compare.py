from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher

from .relations import RELATION_LABELS
from .taxonomy import normalize_ascii


ARTICLE_LABEL_PATTERN = re.compile(r"\bdieu\s+\d+[a-z]?\b", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"[0-9a-z]+")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.;:!?])\s+")

SECTION_TYPES_FOR_MATCHING = {"article", "section", "chapter", "heading", "part"}


def summarize_text(text: str, max_length: int = 340) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3].rstrip() + "..."


def normalize_label(value: str) -> str:
    normalized = normalize_ascii(value)
    normalized = re.sub(r"[^0-9a-z\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def label_tokens(value: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(normalize_label(value)))


def extract_article_label(value: str | None) -> str | None:
    if not value:
        return None
    match = ARTICLE_LABEL_PATTERN.search(normalize_ascii(value))
    return match.group(0) if match else None


def extract_article_labels(value: str | None) -> list[str]:
    if not value:
        return []
    seen: set[str] = set()
    labels: list[str] = []
    for match in ARTICLE_LABEL_PATTERN.findall(normalize_ascii(value)):
        if match not in seen:
            seen.add(match)
            labels.append(match)
    return labels


def extract_distinct_target_article_labels(
    text: str | None, *, self_article: str | None = None
) -> list[str]:
    labels = [
        label
        for label in extract_article_labels(text)
        if label and label != self_article
    ]
    seen: set[str] = set()
    distinct: list[str] = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        distinct.append(label)
    return distinct


def split_clause_units(text: str, max_items: int = 12) -> list[str]:
    collapsed = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [
        segment.strip() for segment in collapsed.split("\n") if segment.strip()
    ]
    units: list[str] = []

    for paragraph in paragraphs:
        if len(paragraph) <= 220:
            units.append(paragraph)
            continue
        pieces = [
            piece.strip() for piece in re.split(r";|•|-\s+", paragraph) if piece.strip()
        ]
        if len(pieces) > 1:
            units.extend(pieces)
        else:
            units.extend(
                [
                    piece.strip()
                    for piece in SENTENCE_SPLIT_PATTERN.split(paragraph)
                    if piece.strip()
                ]
            )

    filtered: list[str] = []
    seen_units: set[str] = set()
    for unit in units:
        short = summarize_text(unit, max_length=200)
        normalized = normalize_label(short)
        if len(normalized) < 12 or normalized in seen_units:
            continue
        seen_units.add(normalized)
        filtered.append(short)
        if len(filtered) >= max_items:
            break
    return filtered


def detect_instruction_type(text: str) -> str:
    normalized = normalize_ascii(text)
    if any(keyword in normalized for keyword in ("bai bo", "huy bo", "thay the")):
        return "repeal"
    if any(keyword in normalized for keyword in ("sua doi", "bo sung", "dinh chinh")):
        return "amendment"
    if any(
        keyword in normalized
        for keyword in ("huong dan", "quy dinh chi tiet", "thi hanh")
    ):
        return "guidance"
    return "reference"


def analyze_text_diff(left_text: str, right_text: str) -> dict:
    left_units = split_clause_units(left_text)
    right_units = split_clause_units(right_text)
    right_matched: set[int] = set()
    changed_pairs: list[dict] = []
    unchanged: list[str] = []
    removed: list[str] = []

    for left_unit in left_units:
        best_index = -1
        best_score = 0.0
        for index, right_unit in enumerate(right_units):
            if index in right_matched:
                continue
            score = SequenceMatcher(
                None, normalize_label(left_unit), normalize_label(right_unit)
            ).ratio()
            if score > best_score:
                best_score = score
                best_index = index

        if best_index >= 0 and best_score >= 0.95:
            unchanged.append(left_unit)
            right_matched.add(best_index)
        elif best_index >= 0 and best_score >= 0.55:
            changed_pairs.append(
                {
                    "left": left_unit,
                    "right": right_units[best_index],
                    "score": round(best_score, 2),
                }
            )
            right_matched.add(best_index)
        else:
            removed.append(left_unit)

    added = [
        right_units[index]
        for index in range(len(right_units))
        if index not in right_matched
    ]

    return {
        "unchanged": unchanged[:3],
        "changed": changed_pairs[:3],
        "removed": removed[:3],
        "added": added[:3],
        "unchanged_count": len(unchanged),
        "changed_count": len(changed_pairs),
        "removed_count": len(removed),
        "added_count": len(added),
    }


def describe_change(
    left_section: dict,
    right_section: dict,
    *,
    reason: str | None,
    lifecycle_compare: bool,
    similarity_score: float,
) -> dict:
    diff = analyze_text_diff(left_section["text"], right_section["text"])

    if lifecycle_compare and reason in {"explicit-citation", "referenced-article"}:
        instruction_type = detect_instruction_type(left_section["text"])
        label_map = {
            "amendment": "amending instruction",
            "repeal": "repeal instruction",
            "guidance": "guidance instruction",
            "reference": "targeted reference",
        }
        summary_map = {
            "amendment": f"This section appears to amend `{right_section['label']}` in the comparison document.",
            "repeal": f"This section appears to repeal or replace part of `{right_section['label']}` in the comparison document.",
            "guidance": f"This section appears to guide or implement `{right_section['label']}` in the comparison document.",
            "reference": f"This section explicitly points to `{right_section['label']}` in the comparison document.",
        }
        return {
            "change_label": label_map[instruction_type],
            "summary": summary_map[instruction_type],
            "details": {
                "instruction_clauses": split_clause_units(
                    left_section["text"], max_items=3
                ),
                "target_excerpt": summarize_text(right_section["text"], max_length=220),
                **diff,
            },
        }

    if (
        similarity_score >= 0.97
        and diff["changed_count"] == diff["added_count"] == diff["removed_count"] == 0
    ):
        return {
            "change_label": "unchanged",
            "summary": "The aligned sections are materially the same in the current local corpus.",
            "details": diff,
        }

    if diff["added_count"] and not diff["removed_count"] and diff["changed_count"] <= 1:
        return {
            "change_label": "expanded",
            "summary": f"The right-side section adds {diff['added_count']} clause(s) or requirement(s) beyond the left-side text.",
            "details": diff,
        }

    if diff["removed_count"] and not diff["added_count"] and diff["changed_count"] <= 1:
        return {
            "change_label": "reduced",
            "summary": f"The right-side section removes or condenses {diff['removed_count']} clause(s) from the left-side text.",
            "details": diff,
        }

    return {
        "change_label": "rewritten",
        "summary": "The aligned sections differ materially and likely need close article-by-article review.",
        "details": diff,
    }


def extract_article_labels(value: str | None) -> list[str]:
    if not value:
        return []
    seen: set[str] = set()
    labels: list[str] = []
    for match in ARTICLE_LABEL_PATTERN.findall(normalize_ascii(value)):
        if match not in seen:
            seen.add(match)
            labels.append(match)
    return labels


def section_similarity(left: dict, right: dict) -> float:
    left_label = normalize_label(left["label"])
    right_label = normalize_label(right["label"])
    label_ratio = SequenceMatcher(None, left_label, right_label).ratio()

    left_tokens = label_tokens(left["label"]) | set(
        TOKEN_PATTERN.findall(normalize_ascii(left["text"][:500]))
    )
    right_tokens = label_tokens(right["label"]) | set(
        TOKEN_PATTERN.findall(normalize_ascii(right["text"][:500]))
    )
    if left_tokens and right_tokens:
        token_score = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    else:
        token_score = 0.0

    return max(label_ratio, token_score)


def get_document_sections(
    connection: sqlite3.Connection, document_id: int
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT id, ordinal, section_type, label, anchor, text
        FROM document_sections
        WHERE document_id = ?
        ORDER BY ordinal ASC
        """,
        (document_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_pair_citation_links(
    connection: sqlite3.Connection, left_document_id: int, right_document_id: int
) -> dict:
    left_to_right_rows = connection.execute(
        """
        SELECT
            cl.link_type,
            s.label AS source_section_label,
            s.anchor AS source_section_anchor,
            m.referenced_label,
            m.cue_phrase
        FROM citation_links cl
        JOIN citation_mentions m ON m.id = cl.mention_id
        JOIN document_sections s ON s.id = m.source_section_id
        WHERE m.source_document_id = ?
          AND cl.target_document_id = ?
        ORDER BY s.ordinal ASC, m.mention_order ASC
        """,
        (left_document_id, right_document_id),
    ).fetchall()

    right_to_left_rows = connection.execute(
        """
        SELECT
            cl.link_type,
            s.label AS source_section_label,
            s.anchor AS source_section_anchor,
            m.referenced_label,
            m.cue_phrase
        FROM citation_links cl
        JOIN citation_mentions m ON m.id = cl.mention_id
        JOIN document_sections s ON s.id = m.source_section_id
        WHERE m.source_document_id = ?
          AND cl.target_document_id = ?
        ORDER BY s.ordinal ASC, m.mention_order ASC
        """,
        (right_document_id, left_document_id),
    ).fetchall()

    return {
        "left_to_right": [dict(row) for row in left_to_right_rows],
        "right_to_left": [dict(row) for row in right_to_left_rows],
    }


def get_pair_relations(
    connection: sqlite3.Connection, left_document_id: int, right_document_id: int
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT relation_type, evidence_text, source_document_id, target_document_id
        FROM document_relations
        WHERE (source_document_id = ? AND target_document_id = ?)
           OR (source_document_id = ? AND target_document_id = ?)
        """,
        (left_document_id, right_document_id, right_document_id, left_document_id),
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        direction = (
            "left_to_right"
            if row["source_document_id"] == left_document_id
            else "right_to_left"
        )
        items.append(
            {
                "direction": direction,
                "relation_type": row["relation_type"],
                "label": RELATION_LABELS[row["relation_type"]],
                "evidence_text": row["evidence_text"],
            }
        )
    return items


def _find_explicit_target_section(
    explicit_links: list[dict],
    left_section: dict,
    right_sections: list[dict],
) -> dict | None:
    candidates = [
        item
        for item in explicit_links
        if item["source_section_anchor"] == left_section["anchor"]
    ]
    if not candidates:
        return None

    for candidate in candidates:
        if candidate.get("referenced_label"):
            normalized_reference = normalize_label(candidate["referenced_label"])
            for right_section in right_sections:
                if normalize_label(right_section["label"]) == normalized_reference:
                    return right_section

    left_article = extract_article_label(left_section["label"])
    article_targets = extract_distinct_target_article_labels(
        left_section["text"], self_article=left_article
    )
    if len(article_targets) == 1:
        article_label = article_targets[0]
        for right_section in right_sections:
            if extract_article_label(right_section["label"]) == article_label:
                return right_section

    if left_article:
        for right_section in right_sections:
            if extract_article_label(right_section["label"]) == left_article:
                return right_section

    return None


def build_compare_alignment(
    left_sections: list[dict],
    right_sections: list[dict],
    explicit_links: list[dict],
    *,
    lifecycle_compare: bool,
    allow_heuristic_matches: bool = True,
) -> dict:
    matched_right_anchors: set[str] = set()
    rows: list[dict] = []

    right_label_index: dict[tuple[str, str], list[dict]] = {}
    right_article_index: dict[str, list[dict]] = {}
    for right_section in right_sections:
        if right_section["section_type"] in SECTION_TYPES_FOR_MATCHING:
            right_label_index.setdefault(
                (
                    right_section["section_type"],
                    normalize_label(right_section["label"]),
                ),
                [],
            ).append(right_section)
        article_label = extract_article_label(right_section["label"])
        if article_label:
            right_article_index.setdefault(article_label, []).append(right_section)

    for left_section in left_sections:
        if left_section["section_type"] not in {"title", *SECTION_TYPES_FOR_MATCHING}:
            continue

        matched_right = _find_explicit_target_section(
            explicit_links, left_section, right_sections
        )
        reason = "explicit-citation" if matched_right else None

        if lifecycle_compare and explicit_links and not matched_right:
            self_article = extract_article_label(left_section["label"])
            article_targets = extract_distinct_target_article_labels(
                left_section["text"], self_article=self_article
            )
            if len(article_targets) == 1:
                article_label = article_targets[0]
                article_candidates = [
                    section
                    for section in right_article_index.get(article_label, [])
                    if section["anchor"] not in matched_right_anchors
                ]
                if article_candidates:
                    matched_right = article_candidates[0]
                    reason = "referenced-article"

        if allow_heuristic_matches and not matched_right:
            label_candidates = right_label_index.get(
                (left_section["section_type"], normalize_label(left_section["label"])),
                [],
            )
            scored = [
                (section_similarity(left_section, right_section), right_section)
                for right_section in label_candidates
                if right_section["anchor"] not in matched_right_anchors
            ]
            scored = [item for item in scored if item[0] >= 0.35]
            scored.sort(key=lambda item: item[0], reverse=True)
            if scored:
                matched_right = scored[0][1]
                reason = "same-label"

        if allow_heuristic_matches and not matched_right:
            article_label = extract_article_label(left_section["label"])
            article_candidates = right_article_index.get(article_label or "", [])
            scored = [
                (section_similarity(left_section, right_section), right_section)
                for right_section in article_candidates
                if right_section["anchor"] not in matched_right_anchors
            ]
            scored = [item for item in scored if item[0] >= 0.3]
            scored.sort(key=lambda item: item[0], reverse=True)
            if scored:
                matched_right = scored[0][1]
                reason = "same-article"

        if allow_heuristic_matches and not matched_right:
            candidates = [
                section
                for section in right_sections
                if section["anchor"] not in matched_right_anchors
                and section["section_type"] == left_section["section_type"]
            ]
            scored = [
                (section_similarity(left_section, right_section), right_section)
                for right_section in candidates
            ]
            scored = [item for item in scored if item[0] >= 0.62]
            scored.sort(key=lambda item: item[0], reverse=True)
            if scored:
                matched_right = scored[0][1]
                reason = "similar-content"

        if matched_right:
            matched_right_anchors.add(matched_right["anchor"])
            score = round(section_similarity(left_section, matched_right), 2)
            change = describe_change(
                left_section,
                matched_right,
                reason=reason,
                lifecycle_compare=lifecycle_compare,
                similarity_score=score,
            )
            rows.append(
                {
                    "kind": "matched",
                    "reason": reason,
                    "left": {
                        **left_section,
                        "summary": summarize_text(left_section["text"]),
                    },
                    "right": {
                        **matched_right,
                        "summary": summarize_text(matched_right["text"]),
                    },
                    "score": score,
                    "change": change,
                }
            )
        else:
            rows.append(
                {
                    "kind": "left-only",
                    "reason": "left-only",
                    "left": {
                        **left_section,
                        "summary": summarize_text(left_section["text"]),
                    },
                    "right": None,
                    "score": 0.0,
                    "change": {
                        "change_label": "unmatched",
                        "summary": "No reliable target section was aligned in the comparison document.",
                        "details": {},
                    },
                }
            )

    right_only = [
        {
            "kind": "right-only",
            "reason": "right-only",
            "left": None,
            "right": {
                **section,
                "summary": summarize_text(section["text"]),
            },
            "score": 0.0,
        }
        for section in right_sections
        if section["anchor"] not in matched_right_anchors
        and section["section_type"] in {"title", *SECTION_TYPES_FOR_MATCHING}
    ]

    return {
        "rows": rows,
        "right_only": right_only,
        "matched_count": sum(1 for row in rows if row["kind"] == "matched"),
        "left_only_count": sum(1 for row in rows if row["kind"] == "left-only"),
        "right_only_count": len(right_only),
        "explicit_match_count": sum(
            1
            for row in rows
            if row["reason"] in {"explicit-citation", "referenced-article"}
        ),
        "change_counts": {
            "unchanged": sum(
                1
                for row in rows
                if row["kind"] == "matched"
                and row["change"]["change_label"] == "unchanged"
            ),
            "expanded": sum(
                1
                for row in rows
                if row["kind"] == "matched"
                and row["change"]["change_label"] == "expanded"
            ),
            "reduced": sum(
                1
                for row in rows
                if row["kind"] == "matched"
                and row["change"]["change_label"] == "reduced"
            ),
            "rewritten": sum(
                1
                for row in rows
                if row["kind"] == "matched"
                and row["change"]["change_label"] == "rewritten"
            ),
            "instruction": sum(
                1
                for row in rows
                if row["kind"] == "matched"
                and row["change"]["change_label"]
                in {
                    "amending instruction",
                    "repeal instruction",
                    "guidance instruction",
                    "targeted reference",
                }
            ),
        },
    }


def build_compare_view(
    connection: sqlite3.Connection, left_document: dict, right_document: dict
) -> dict:
    left_sections = get_document_sections(connection, left_document["id"])
    right_sections = get_document_sections(connection, right_document["id"])
    pair_citations = get_pair_citation_links(
        connection, left_document["id"], right_document["id"]
    )
    pair_relations = get_pair_relations(
        connection, left_document["id"], right_document["id"]
    )
    lifecycle_compare = any(
        item["relation_type"] in {"amends", "replaces"} for item in pair_relations
    ) or any(
        item["link_type"] in {"amends", "replaces"}
        for item in pair_citations["left_to_right"] + pair_citations["right_to_left"]
    )
    alignment = build_compare_alignment(
        left_sections,
        right_sections,
        pair_citations["left_to_right"],
        lifecycle_compare=lifecycle_compare,
        allow_heuristic_matches=not lifecycle_compare,
    )

    return {
        "left_document": left_document,
        "right_document": right_document,
        "pair_citations": pair_citations,
        "pair_relations": pair_relations,
        "alignment": alignment,
        "lifecycle_compare": lifecycle_compare,
    }


def pick_compare_target(
    relation_graph: dict, citation_graph: dict, related_documents: list[dict]
) -> dict | None:
    relation_priorities = (
        (relation_graph.get("incoming", []), {"replaces", "amends"}, "newer-change"),
        (relation_graph.get("outgoing", []), {"replaces", "amends"}, "older-change"),
    )
    for groups, relation_types, reason in relation_priorities:
        for group in groups:
            if group.get("key", "").replace("_incoming", "") not in relation_types:
                continue
            if group.get("items"):
                item = group["items"][0]
                return {
                    "id": item["id"],
                    "title": item["title"],
                    "document_number": item.get("document_number"),
                    "legal_type": item.get("legal_type"),
                    "issuance_date": item.get("issuance_date"),
                    "reason": reason,
                }

    citation_priorities = (
        (
            citation_graph.get("incoming_groups", []),
            {"replaces_incoming", "amends_incoming"},
            "newer-citation",
        ),
        (
            citation_graph.get("outgoing_groups", []),
            {"replaces", "amends"},
            "outgoing-citation",
        ),
    )
    for groups, citation_keys, reason in citation_priorities:
        for group in groups:
            if group.get("key") not in citation_keys:
                continue
            if group.get("items"):
                item = group["items"][0]
                return {
                    "id": item["id"],
                    "title": item["title"],
                    "document_number": item.get("document_number"),
                    "legal_type": item.get("legal_type"),
                    "issuance_date": item.get("issuance_date"),
                    "reason": reason,
                }

    if related_documents:
        item = related_documents[0]
        return {
            "id": item["id"],
            "title": item["title"],
            "document_number": item.get("document_number"),
            "legal_type": item.get("legal_type"),
            "issuance_date": item.get("issuance_date"),
            "reason": "related-document",
        }
    return None


def _pick_focus_alignment_row(
    compare_view: dict,
    *,
    focus_left_anchor: str | None = None,
    focus_right_anchor: str | None = None,
) -> dict | None:
    rows = compare_view["alignment"]["rows"]

    if focus_left_anchor:
        for row in rows:
            if row.get("left") and row["left"].get("anchor") == focus_left_anchor:
                return row

    if focus_right_anchor:
        for row in rows:
            if row.get("right") and row["right"].get("anchor") == focus_right_anchor:
                return row

    for row in rows:
        if row["kind"] == "matched" and row["change"]["change_label"] != "unchanged":
            return row

    for row in rows:
        if row["kind"] == "matched":
            return row

    return rows[0] if rows else None


def build_compare_focus_preview(
    connection: sqlite3.Connection,
    left_document: dict,
    right_document: dict,
    *,
    focus_left_anchor: str | None = None,
    focus_right_anchor: str | None = None,
) -> dict | None:
    compare_view = build_compare_view(connection, left_document, right_document)
    row = _pick_focus_alignment_row(
        compare_view,
        focus_left_anchor=focus_left_anchor,
        focus_right_anchor=focus_right_anchor,
    )
    if not row:
        return None

    change = row.get("change") or {}
    details = change.get("details") or {}
    changed_pairs = details.get("changed") or []
    return {
        "compare_path": f"/compare/{left_document['id']}/{right_document['id']}",
        "comparison_document": {
            "id": right_document["id"],
            "title": right_document["title"],
            "document_number": right_document.get("document_number"),
            "legal_type": right_document.get("legal_type"),
            "issuance_date": right_document.get("issuance_date"),
        },
        "focus": {
            "left": {
                "label": row.get("left", {}).get("label"),
                "anchor": row.get("left", {}).get("anchor"),
                "summary": row.get("left", {}).get("summary"),
            }
            if row.get("left")
            else None,
            "right": {
                "label": row.get("right", {}).get("label"),
                "anchor": row.get("right", {}).get("anchor"),
                "summary": row.get("right", {}).get("summary"),
            }
            if row.get("right")
            else None,
        },
        "change": {
            "label": change.get("change_label"),
            "summary": change.get("summary"),
            "score": row.get("score"),
            "added": details.get("added", [])[:2],
            "removed": details.get("removed", [])[:2],
            "changed": changed_pairs[:2],
            "instruction_clauses": details.get("instruction_clauses", [])[:2],
        },
    }

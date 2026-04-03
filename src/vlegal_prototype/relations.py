from __future__ import annotations

import re
import sqlite3

from .taxonomy import normalize_ascii


DOC_NUMBER_PATTERN = re.compile(
    r"\b\d+[a-z]?(?:[/-]\d{2,4})?(?:[/-][0-9a-z]*[a-z][0-9a-z]*)+\b"
)
CONTEXTUAL_DOC_REFERENCE_PATTERN = re.compile(
    r"\b(bo luat|luat|phap lenh|sac lenh|lenh|nghi quyet|nghi dinh|quyet dinh|chi thi|thong tu lien tich|thong tu)\s*(?:so\s*[:.]?\s*)?(\d{1,4}(?:[/-]\d{2,4})?(?:[/-][0-9a-z]+)?)\b"
)

LEGAL_TYPE_ABBREVIATIONS = {
    "sac lenh": {"sl"},
    "phap lenh": {"pl"},
    "nghi dinh": {"nd", "nd-cp"},
    "nghi quyet": {"nq", "nq-cp", "nq-hdnd", "nq-qh"},
    "quyet dinh": {"qd", "qd-ttg", "qd-ubnd"},
    "chi thi": {"ct", "ct-ttg", "ct-ubnd"},
    "thong tu": {"tt"},
    "thong tu lien tich": {"ttlt"},
    "luat": {"qh"},
    "bo luat": {"qh"},
    "lenh": {"l"},
}

GENERIC_LOCAL_MARKERS = (
    "qd-ubnd",
    "kh-ubnd",
    "ct-ubnd",
    "tb-ubnd",
    "nq-hdnd",
    "qd-hdnd",
)

RELATION_PATTERNS = {
    "replaces": (
        re.compile(r"\bbai bo(?: toan bo)?\b"),
        re.compile(r"\bthay the\b"),
        re.compile(r"\bhuy bo\b"),
    ),
    "amends": (
        re.compile(r"\bsua doi(?:, bo sung)?\b"),
        re.compile(r"\bbo sung mot so dieu\b"),
        re.compile(r"\bdinh chinh\b"),
    ),
    "guides": (
        re.compile(r"\bhuong dan(?: thi hanh| thuc hien)?\b"),
        re.compile(r"\bquy dinh chi tiet\b"),
        re.compile(r"\btrien khai thuc hien\b"),
    ),
}

RELATION_LABELS = {
    "amends": "Amends",
    "replaces": "Replaces",
    "guides": "Guides",
}

INVERSE_RELATION_LABELS = {
    "amends": "Amended by",
    "replaces": "Replaced by",
    "guides": "Guided by",
}

RELATION_ORDER = ("amends", "replaces", "guides")


def normalize_document_number(value: str | None) -> str:
    normalized = normalize_ascii(value or "")
    normalized = re.sub(r"[^0-9a-z/-]", "", normalized)
    return normalized


def normalize_legal_type_hint(value: str | None) -> str:
    return re.sub(r"\s+", " ", normalize_ascii(value or "")).strip()


def split_document_number_parts(value: str) -> list[str]:
    return [part for part in re.split(r"[/-]", value) if part]


def get_legal_type_abbreviations(legal_type: str | None) -> set[str]:
    return LEGAL_TYPE_ABBREVIATIONS.get(normalize_legal_type_hint(legal_type), set())


def build_document_number_aliases(
    document_number: str | None, legal_type: str | None = None
) -> set[str]:
    normalized = normalize_document_number(document_number)
    if not normalized:
        return set()

    aliases = {normalized, normalized.replace("-", "/"), normalized.replace("/", "-")}
    parts = split_document_number_parts(normalized)
    if not parts:
        return aliases

    base = parts[0]
    if len(parts) > 1 and any(char.isalpha() for char in parts[-1]):
        aliases.add(base)

    for abbreviation in get_legal_type_abbreviations(legal_type):
        aliases.add(f"{base}/{abbreviation}")
        aliases.add(f"{base}-{abbreviation}")
    return aliases


def build_sql_document_number_aliases(
    document_number: str | None, legal_type: str | None = None
) -> list[str]:
    values: set[str] = set()
    for alias in build_document_number_aliases(document_number, legal_type):
        values.add(alias)
        values.add(alias.upper())
        values.add(alias.replace("/", "-").upper())
        values.add(alias.replace("-", "/").upper())
    return sorted(values)


def iter_document_reference_matches(text: str) -> list[dict]:
    normalized = normalize_ascii(text)
    matches: list[dict] = []

    for match in DOC_NUMBER_PATTERN.finditer(normalized):
        matches.append(
            {
                "raw_reference": match.group(0),
                "referenced_number": normalize_document_number(match.group(0)),
                "legal_type_hint": None,
                "start": match.start(),
                "end": match.end(),
            }
        )

    for match in CONTEXTUAL_DOC_REFERENCE_PATTERN.finditer(normalized):
        raw_reference = match.group(2)
        matches.append(
            {
                "raw_reference": raw_reference,
                "referenced_number": normalize_document_number(raw_reference),
                "legal_type_hint": match.group(1),
                "start": match.start(2),
                "end": match.end(2),
            }
        )

    deduped: list[dict] = []
    seen: set[tuple[int, int, str]] = set()
    for item in sorted(
        matches,
        key=lambda value: (
            value["start"],
            -(1 if value.get("legal_type_hint") else 0),
            -(value["end"] - value["start"]),
        ),
    ):
        key = (item["start"], item["end"], item["referenced_number"])
        if not item["referenced_number"] or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def extract_document_numbers(text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in iter_document_reference_matches(text):
        doc_number = item["referenced_number"]
        if doc_number and doc_number not in seen:
            seen.add(doc_number)
            values.append(doc_number)
    return values


def extract_localities(text: str) -> set[str]:
    normalized = normalize_ascii(text)
    tokens = normalized.split()
    localities: set[str] = set()
    stopwords = {
        "giai",
        "doan",
        "tren",
        "dia",
        "ban",
        "kem",
        "theo",
        "do",
        "hanh",
        "quy",
        "dinh",
        "ve",
        "cua",
        "thuc",
        "hien",
    }

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "tinh":
            phrase = [token]
            for next_token in tokens[index + 1 : index + 4]:
                if next_token in stopwords or not re.fullmatch(r"[a-z]+", next_token):
                    break
                phrase.append(next_token)
            if len(phrase) >= 2:
                localities.add(" ".join(phrase))
        if token == "thanh" and index + 1 < len(tokens) and tokens[index + 1] == "pho":
            phrase = [token, "pho"]
            for next_token in tokens[index + 2 : index + 5]:
                if next_token in stopwords or not re.fullmatch(r"[a-z]+", next_token):
                    break
                phrase.append(next_token)
            if len(phrase) >= 3:
                localities.add(" ".join(phrase))
        index += 1
    return localities


def requires_local_context(referenced_number: str) -> bool:
    return any(marker in referenced_number for marker in GENERIC_LOCAL_MARKERS)


def candidate_has_valid_context(
    source_document: dict, candidate: dict, referenced_number: str
) -> bool:
    if not requires_local_context(referenced_number):
        return True

    source_issuer = normalize_ascii(source_document.get("issuing_authority") or "")
    candidate_issuer = normalize_ascii(candidate.get("issuing_authority") or "")
    if source_issuer and candidate_issuer:
        return source_issuer == candidate_issuer

    source_text = " ".join(
        filter(
            None,
            [
                source_document.get("title") or "",
                source_document.get("issuing_authority") or "",
            ],
        )
    )
    candidate_text = " ".join(
        filter(
            None,
            [candidate.get("title") or "", candidate.get("issuing_authority") or ""],
        )
    )

    source_localities = extract_localities(source_text)
    candidate_localities = extract_localities(candidate_text)
    if source_localities:
        return bool(candidate_localities) and not source_localities.isdisjoint(
            candidate_localities
        )
    return True


def extract_relation_candidates(text: str) -> list[dict]:
    normalized = normalize_ascii(text)
    candidates: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for relation_type, patterns in RELATION_PATTERNS.items():
        for pattern in patterns:
            for match in pattern.finditer(normalized):
                segment = normalized[match.start() : match.start() + 420]
                for reference in iter_document_reference_matches(segment):
                    referenced_number = reference["referenced_number"]
                    legal_type_hint = reference.get("legal_type_hint") or ""
                    key = (relation_type, referenced_number, legal_type_hint)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(
                        {
                            "relation_type": relation_type,
                            "referenced_number": referenced_number,
                            "legal_type_hint": reference.get("legal_type_hint"),
                        }
                    )
    return candidates


def build_document_number_index(
    connection: sqlite3.Connection,
) -> dict[str, list[dict]]:
    rows = connection.execute(
        """
        SELECT id, document_number, legal_type, issuing_authority, title, year
        FROM documents
        WHERE COALESCE(document_number, '') <> ''
        """
    ).fetchall()

    index: dict[str, list[dict]] = {}
    for row in rows:
        candidate = dict(row)
        for key in build_document_number_aliases(
            row["document_number"], row["legal_type"]
        ):
            index.setdefault(key, []).append(candidate)
    return index


def choose_target_document(
    source_document: dict,
    referenced_number: str,
    index: dict[str, list[dict]],
    reference_legal_type: str | None = None,
    reference_year: int | None = None,
    reference_context_text: str | None = None,
) -> dict | None:
    normalized_reference = normalize_document_number(referenced_number)
    candidates_by_id: dict[int, dict] = {}
    for key in build_document_number_aliases(referenced_number, reference_legal_type):
        for candidate in index.get(key, []):
            if candidate["id"] == source_document["id"]:
                continue
            candidates_by_id[candidate["id"]] = candidate
    candidates = list(candidates_by_id.values())
    if not candidates:
        return None

    normalized_legal_type_hint = normalize_legal_type_hint(reference_legal_type)
    if normalized_legal_type_hint:
        typed_candidates = [
            candidate
            for candidate in candidates
            if normalize_legal_type_hint(candidate.get("legal_type"))
            == normalized_legal_type_hint
        ]
        if typed_candidates:
            candidates = typed_candidates

    if reference_year is not None:
        same_year_candidates = [
            candidate
            for candidate in candidates
            if candidate.get("year") == reference_year
            and candidate_has_valid_context(
                source_document, candidate, referenced_number
            )
        ]
        if len(same_year_candidates) == 1:
            return same_year_candidates[0]
        if same_year_candidates:
            candidates = same_year_candidates

    if normalized_legal_type_hint:
        base_reference = split_document_number_parts(normalized_reference)[0]
        suffix_candidates = []
        for candidate in candidates:
            normalized_candidate = normalize_document_number(
                candidate.get("document_number")
            )
            parts = split_document_number_parts(normalized_candidate)
            if not parts or parts[0] != base_reference:
                continue
            if len(parts) > 1 and any(char.isalpha() for char in parts[-1]):
                suffix_candidates.append(candidate)
        if suffix_candidates:
            candidates = suffix_candidates

    if len(candidates) == 1:
        return (
            candidates[0]
            if candidate_has_valid_context(
                source_document, candidates[0], referenced_number
            )
            else None
        )

    source_issuer = normalize_ascii(source_document.get("issuing_authority") or "")
    if source_issuer:
        same_issuer = [
            candidate
            for candidate in candidates
            if normalize_ascii(candidate.get("issuing_authority") or "")
            == source_issuer
            and candidate_has_valid_context(
                source_document, candidate, referenced_number
            )
        ]
        if len(same_issuer) == 1:
            return same_issuer[0]

    source_title_tokens = set(
        normalize_ascii(source_document.get("title") or "").split()
    )
    reference_context_tokens = set(
        normalize_ascii(reference_context_text or "").split()
    )
    reference_aliases = build_document_number_aliases(
        referenced_number, reference_legal_type
    )
    scored_candidates: list[tuple[int, dict]] = []
    for candidate in candidates:
        title_tokens = set(normalize_ascii(candidate.get("title") or "").split())
        issuer_tokens = set(
            normalize_ascii(candidate.get("issuing_authority") or "").split()
        )
        overlap = len(source_title_tokens & issuer_tokens)
        score = overlap
        if (
            normalize_legal_type_hint(candidate.get("legal_type"))
            == normalized_legal_type_hint
        ):
            score += 5
        if reference_year is not None and candidate.get("year") == reference_year:
            score += 6
        if (
            normalize_document_number(candidate.get("document_number"))
            in reference_aliases
        ):
            score += 3
        if reference_context_tokens:
            score += min(len(reference_context_tokens & title_tokens), 6)
        scored_candidates.append((score, candidate))

    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    if (
        len(scored_candidates) >= 2
        and scored_candidates[0][0] > scored_candidates[1][0]
        and candidate_has_valid_context(
            source_document, scored_candidates[0][1], referenced_number
        )
    ):
        return scored_candidates[0][1]
    return None


def resolve_target_document(
    connection: sqlite3.Connection,
    source_document: dict,
    referenced_number: str,
    reference_legal_type: str | None = None,
    reference_year: int | None = None,
    reference_context_text: str | None = None,
) -> dict | None:
    aliases = build_sql_document_number_aliases(referenced_number, reference_legal_type)
    if not aliases:
        return None

    placeholders = ", ".join("?" for _ in aliases)
    rows = connection.execute(
        f"""
        SELECT id, document_number, legal_type, issuing_authority, title, year
        FROM documents
        WHERE document_number IN ({placeholders})
        """,
        aliases,
    ).fetchall()
    if not rows:
        return None

    index: dict[str, list[dict]] = {}
    for row in rows:
        candidate = dict(row)
        for key in build_document_number_aliases(
            candidate.get("document_number"), candidate.get("legal_type")
        ):
            index.setdefault(key, []).append(candidate)

    return choose_target_document(
        source_document,
        referenced_number,
        index,
        reference_legal_type=reference_legal_type,
        reference_year=reference_year,
        reference_context_text=reference_context_text,
    )


def rebuild_relationship_graph(connection: sqlite3.Connection) -> int:
    documents = [
        dict(row)
        for row in connection.execute(
            """
            SELECT id, document_number, legal_type, title, issuing_authority, year
            FROM documents
            """
        ).fetchall()
    ]
    number_index = build_document_number_index(connection)

    relation_rows: list[tuple[int, int, str, str, str]] = []
    seen: set[tuple[int, int, str]] = set()

    for document in documents:
        for candidate in extract_relation_candidates(document["title"]):
            target = choose_target_document(
                document,
                candidate["referenced_number"],
                number_index,
                reference_legal_type=candidate.get("legal_type_hint"),
            )
            if not target:
                continue
            key = (document["id"], target["id"], candidate["relation_type"])
            if key in seen:
                continue
            seen.add(key)
            relation_rows.append(
                (
                    document["id"],
                    target["id"],
                    candidate["relation_type"],
                    document["title"],
                    "high",
                )
            )

    with connection:
        connection.execute("DELETE FROM document_relations")
        connection.executemany(
            """
            INSERT INTO document_relations (
                source_document_id,
                target_document_id,
                relation_type,
                evidence_text,
                confidence
            ) VALUES (?, ?, ?, ?, ?)
            """,
            relation_rows,
        )
    return len(relation_rows)


def get_relation_count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM document_relations").fetchone()[0]


def _group_relation_rows(rows: list[sqlite3.Row], direction: str) -> list[dict]:
    label_map = RELATION_LABELS if direction == "outgoing" else INVERSE_RELATION_LABELS
    grouped = {relation_type: [] for relation_type in RELATION_ORDER}
    for row in rows:
        grouped[row["relation_type"]].append(dict(row))

    groups: list[dict] = []
    for relation_type in RELATION_ORDER:
        items = grouped[relation_type]
        if not items:
            continue
        groups.append(
            {
                "key": relation_type
                if direction == "outgoing"
                else f"{relation_type}_incoming",
                "label": label_map[relation_type],
                "items": items,
            }
        )
    return groups


def get_document_relation_graph(
    connection: sqlite3.Connection, document_id: int
) -> dict:
    outgoing_rows = connection.execute(
        """
        SELECT
            r.relation_type,
            d.id,
            d.title,
            d.document_number,
            d.legal_type,
            d.issuance_date,
            r.evidence_text,
            r.confidence
        FROM document_relations r
        JOIN documents d ON d.id = r.target_document_id
        WHERE r.source_document_id = ?
        ORDER BY d.year DESC, d.title ASC
        """,
        (document_id,),
    ).fetchall()

    incoming_rows = connection.execute(
        """
        SELECT
            r.relation_type,
            d.id,
            d.title,
            d.document_number,
            d.legal_type,
            d.issuance_date,
            r.evidence_text,
            r.confidence
        FROM document_relations r
        JOIN documents d ON d.id = r.source_document_id
        WHERE r.target_document_id = ?
        ORDER BY d.year DESC, d.title ASC
        """,
        (document_id,),
    ).fetchall()

    return {
        "incoming": _group_relation_rows(list(incoming_rows), "incoming"),
        "outgoing": _group_relation_rows(list(outgoing_rows), "outgoing"),
        "total": len(incoming_rows) + len(outgoing_rows),
    }

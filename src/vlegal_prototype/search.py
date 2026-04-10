from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from .taxonomy import normalize_ascii


TOKEN_PATTERN = re.compile(r"[0-9A-Za-zÀ-ỹ]+", re.UNICODE)
IDENTIFIER_HINT_PATTERN = re.compile(r"\d")
NORMALIZED_TOKEN_PATTERN = re.compile(r"[0-9a-z]+")

PASSAGE_RERANK_STOPWORDS = {
    "ban",
    "bo",
    "cac",
    "can",
    "cho",
    "co",
    "cua",
    "da",
    "de",
    "den",
    "dieu",
    "duoc",
    "khoan",
    "la",
    "luat",
    "muc",
    "mot",
    "ngay",
    "nghi",
    "nhung",
    "noi",
    "phap",
    "quyet",
    "so",
    "tai",
    "theo",
    "thong",
    "trong",
    "tu",
    "van",
    "ve",
    "viec",
    "voi",
}

FOCUS_QUERY_STOPWORDS = {
    "ban",
    "bo",
    "dinh",
    "dung",
    "gi",
    "huong",
    "luat",
    "muc",
    "nao",
    "nghi",
    "noi",
    "quy",
    "quyet",
    "thong",
    "trinh",
    "tu",
    "van",
    "ve",
    "viec",
}

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def normalize_query_text(value: str) -> str:
    normalized = normalize_ascii(value)
    normalized = re.sub(r"[^0-9a-z/\s-]", " ", normalized)
    return " ".join(normalized.split())


def tokenize_query_terms(value: str) -> set[str]:
    return {
        token
        for token in NORMALIZED_TOKEN_PATTERN.findall(normalize_query_text(value))
        if len(token) >= 2 and token not in PASSAGE_RERANK_STOPWORDS
    }


def build_focus_query(raw_query: str) -> str:
    tokens = TOKEN_PATTERN.findall(raw_query)
    if not tokens:
        return raw_query.strip()
    filtered = [
        token
        for token in tokens
        if any(char.isdigit() for char in token)
        or normalize_query_text(token) not in FOCUS_QUERY_STOPWORDS
    ]
    if filtered and len(filtered) < len(tokens):
        return " ".join(filtered[:8])
    return raw_query.strip()


def score_passage_match(
    query: str, row: dict, document_rank_map: dict[int, int] | None = None
) -> float:
    normalized_query = normalize_query_text(query)
    important_terms = tokenize_query_terms(query)
    normalized_title = normalize_query_text(row.get("title") or "")
    normalized_heading = normalize_query_text(row.get("heading") or "")
    normalized_text = normalize_query_text(row.get("text") or "")
    score = float(-row.get("rank", 0.0))

    if document_rank_map:
        rank = document_rank_map.get(int(row.get("document_id") or 0))
        if rank is not None:
            score += max(0.0, 24.0 - rank)

    if normalized_query and normalized_query in normalized_title:
        score += 14.0
    if normalized_query and normalized_query in normalized_heading:
        score += 10.0
    if normalized_query and normalized_query in normalized_text:
        score += 8.0

    for term in important_terms:
        if term in normalized_title:
            score += 3.0
        if term in normalized_heading:
            score += 2.0
        if term in normalized_text:
            score += 1.0

    if normalized_heading.startswith("dieu "):
        score += 0.25

    return score


def rerank_passages(
    query: str,
    rows: list[dict],
    limit: int,
    *,
    document_rank_map: dict[int, int] | None = None,
) -> list[dict]:
    ranked = sorted(
        rows,
        key=lambda item: (
            score_passage_match(query, item, document_rank_map=document_rank_map),
            item.get("issuance_date") or "",
            item.get("ordinal") or 0,
        ),
        reverse=True,
    )
    return ranked[:limit]


def strip_html_tags(value: str | None) -> str:
    cleaned = HTML_TAG_PATTERN.sub(" ", value or "")
    return " ".join(cleaned.split())


def build_overview_passages(document_results: dict, limit: int = 8) -> list[dict]:
    overview_rows: list[dict] = []
    for index, item in enumerate(document_results.get("items", [])[:limit]):
        text_parts = [item.get("title") or ""]
        snippet = strip_html_tags(item.get("snippet") or "")
        if snippet and snippet not in text_parts:
            text_parts.append(snippet)
        overview_rows.append(
            {
                "id": f"overview-{item['id']}",
                "document_id": item["id"],
                "ordinal": 0,
                "heading": "Tieu de",
                "text": ". ".join(part for part in text_parts if part),
                "title": item.get("title") or "",
                "document_number": item.get("document_number") or "",
                "legal_type": item.get("legal_type") or "",
                "issuing_authority": item.get("issuing_authority") or "",
                "issuance_date": item.get("issuance_date") or "",
                "url": item.get("url") or "",
                "rank": float(-(limit - index + 1)),
            }
        )
    return overview_rows


def to_fts_query(raw_query: str) -> str:
    tokens = [token for token in TOKEN_PATTERN.findall(raw_query) if len(token) >= 2]
    if not tokens:
        return ""
    return " AND ".join(f'"{token}"*' for token in tokens[:10])


def normalize_identifier_query(raw_query: str) -> str:
    collapsed = re.sub(r"\s+", "", raw_query.strip())
    return collapsed.upper().replace("-", "/")


def looks_like_identifier_query(raw_query: str) -> bool:
    query = raw_query.strip()
    if not query:
        return False
    return bool(IDENTIFIER_HINT_PATTERN.search(query)) and len(query) <= 64


def search_identifier_documents(
    connection: sqlite3.Connection,
    query: str,
    page: int,
    page_size: int,
    filters: list[str],
    filter_params: list[object],
) -> dict:
    normalized_query = normalize_identifier_query(query)
    if not normalized_query:
        return {"items": [], "page": page, "page_count": 0, "total": 0}

    number_expr = "REPLACE(UPPER(COALESCE(d.document_number, '')), '-', '/')"
    title_like = f"%{query.strip().upper()}%"
    prefix_slash = f"{normalized_query}/%"
    prefix_general = f"{normalized_query}%"
    predicates = [
        f"{number_expr} = ?",
        f"{number_expr} LIKE ?",
        f"{number_expr} LIKE ?",
        "UPPER(d.title) LIKE ?",
    ]
    predicate_params: list[object] = [
        normalized_query,
        prefix_slash,
        prefix_general,
        title_like,
    ]

    where_terms = [f"({' OR '.join(predicates)})", *filters]
    where_clause = " AND ".join(where_terms)
    offset = (page - 1) * page_size

    count_sql = f"""
        SELECT COUNT(*)
        FROM documents d
        WHERE {where_clause}
    """
    total = connection.execute(
        count_sql, [*predicate_params, *filter_params]
    ).fetchone()[0]
    if not total:
        return {"items": [], "page": page, "page_count": 0, "total": 0}

    max_reasonable_year = datetime.utcnow().year + 1
    sql = f"""
        SELECT
            d.id,
            d.document_number,
            d.title,
            d.legal_type,
            d.issuing_authority,
            d.issuance_date,
            d.legal_sectors,
            d.url,
            d.excerpt AS snippet,
            CASE
                WHEN {number_expr} = ? THEN 0
                WHEN {number_expr} LIKE ? THEN 1
                WHEN {number_expr} LIKE ? THEN 2
                WHEN UPPER(d.title) LIKE ? THEN 3
                ELSE 4
            END AS match_rank,
            ABS(LENGTH(COALESCE(d.document_number, '')) - ?) AS number_delta
        FROM documents d
        WHERE {where_clause}
        ORDER BY
            match_rank ASC,
            number_delta ASC,
            CASE WHEN d.year BETWEEN 1800 AND ? THEN d.year END DESC,
            d.issuance_date DESC,
            d.title ASC
        LIMIT ? OFFSET ?
    """
    rows = connection.execute(
        sql,
        [
            *predicate_params,
            len(normalized_query),
            *predicate_params,
            *filter_params,
            max_reasonable_year,
            page_size,
            offset,
        ],
    ).fetchall()
    page_count = (total + page_size - 1) // page_size if total else 0
    return {
        "items": [dict(row) for row in rows],
        "page": page,
        "page_count": page_count,
        "total": total,
    }


def search_retrieval_documents(
    connection: sqlite3.Connection,
    query: str,
    page: int,
    page_size: int,
    filters: list[str],
    filter_params: list[object],
) -> dict:
    fts_query = to_fts_query(query)
    if not fts_query:
        return {"items": [], "page": page, "page_count": 0, "total": 0}

    where_clause = (
        " AND ".join(["document_retrieval_fts MATCH ?", *filters])
        if filters
        else "document_retrieval_fts MATCH ?"
    )
    count_sql = f"""
        SELECT COUNT(*)
        FROM document_retrieval_fts
        JOIN document_retrieval_profiles dr ON dr.document_id = document_retrieval_fts.rowid
        JOIN documents d ON d.id = dr.document_id
        WHERE {where_clause}
    """
    total = connection.execute(count_sql, [fts_query, *filter_params]).fetchone()[0]
    if not total:
        return {"items": [], "page": page, "page_count": 0, "total": 0}

    offset = (page - 1) * page_size
    sql = f"""
        SELECT
            d.id,
            d.document_number,
            d.title,
            d.legal_type,
            d.issuing_authority,
            d.issuance_date,
            d.legal_sectors,
            d.url,
            COALESCE(
                NULLIF(snippet(document_retrieval_fts, 0, '<mark>', '</mark>', ' ... ', 10), ''),
                NULLIF(snippet(document_retrieval_fts, 1, '<mark>', '</mark>', ' ... ', 10), ''),
                NULLIF(snippet(document_retrieval_fts, 2, '<mark>', '</mark>', ' ... ', 10), ''),
                d.excerpt
            ) AS snippet,
            bm25(document_retrieval_fts, 3.0, 2.5, 2.0, 1.0) AS rank
        FROM document_retrieval_fts
        JOIN document_retrieval_profiles dr ON dr.document_id = document_retrieval_fts.rowid
        JOIN documents d ON d.id = dr.document_id
        WHERE {where_clause}
        ORDER BY rank, d.year DESC, d.title ASC
        LIMIT ? OFFSET ?
    """
    rows = connection.execute(
        sql, [fts_query, *filter_params, page_size, offset]
    ).fetchall()
    page_count = (total + page_size - 1) // page_size if total else 0
    return {
        "items": [dict(row) for row in rows],
        "page": page,
        "page_count": page_count,
        "total": total,
    }


def retrieve_candidate_document_ids(
    connection: sqlite3.Connection, query: str, limit: int = 48
) -> list[int]:
    fts_query = to_fts_query(query)
    if not fts_query:
        return []
    rows = connection.execute(
        """
        SELECT dr.document_id
        FROM document_retrieval_fts
        JOIN document_retrieval_profiles dr ON dr.document_id = document_retrieval_fts.rowid
        WHERE document_retrieval_fts MATCH ?
        ORDER BY bm25(document_retrieval_fts, 3.0, 2.5, 2.0, 1.0)
        LIMIT ?
        """,
        (fts_query, limit),
    ).fetchall()
    return [int(row[0]) for row in rows]


def get_filter_options(connection: sqlite3.Connection) -> dict:
    legal_types = [
        row[0]
        for row in connection.execute(
            """
            SELECT legal_type
            FROM documents
            WHERE COALESCE(legal_type, '') <> ''
            GROUP BY legal_type
            ORDER BY COUNT(*) DESC, legal_type ASC
            LIMIT 12
            """
        ).fetchall()
    ]
    years = [
        row[0]
        for row in connection.execute(
            """
            SELECT year
            FROM documents
            WHERE year IS NOT NULL
            GROUP BY year
            ORDER BY year DESC
            LIMIT 20
            """
        ).fetchall()
    ]
    return {"legal_types": legal_types, "years": years}


def get_top_legal_types(connection: sqlite3.Connection, limit: int = 6) -> list[dict]:
    rows = connection.execute(
        """
        SELECT legal_type, COUNT(*) AS total
        FROM documents
        WHERE COALESCE(legal_type, '') <> ''
        GROUP BY legal_type
        ORDER BY total DESC, legal_type ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_recent_documents(connection: sqlite3.Connection, limit: int = 5) -> list[dict]:
    max_reasonable_year = datetime.utcnow().year + 1
    rows = connection.execute(
        """
        SELECT id, title, document_number, legal_type, issuing_authority, issuance_date, excerpt
        FROM documents
        ORDER BY
            CASE WHEN year BETWEEN 1800 AND ? THEN year END DESC,
            CASE WHEN year BETWEEN 1800 AND ? THEN issuance_date END DESC,
            id DESC
        LIMIT ?
        """,
        (max_reasonable_year, max_reasonable_year, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def get_tracked_documents(connection: sqlite3.Connection, limit: int = 8) -> list[dict]:
    rows = connection.execute(
        """
        SELECT d.id, d.title, d.document_number, d.legal_type, d.issuing_authority, d.issuance_date, d.year, t.tracked_at
        FROM tracked_documents t
        JOIN documents d ON d.id = t.document_id
        ORDER BY t.tracked_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_tracked_document_ids(
    connection: sqlite3.Connection, document_ids: list[int] | None = None
) -> set[int]:
    if document_ids:
        placeholders = ", ".join("?" for _ in document_ids)
        sql = f"SELECT document_id FROM tracked_documents WHERE document_id IN ({placeholders})"
        rows = connection.execute(sql, document_ids).fetchall()
    else:
        rows = connection.execute(
            "SELECT document_id FROM tracked_documents"
        ).fetchall()
    return {row[0] for row in rows}


def set_document_tracking(
    connection: sqlite3.Connection, document_id: int, tracked: bool
) -> bool:
    exists = connection.execute(
        "SELECT 1 FROM documents WHERE id = ?",
        (document_id,),
    ).fetchone()
    if not exists:
        return False

    with connection:
        if tracked:
            connection.execute(
                "INSERT OR IGNORE INTO tracked_documents (document_id) VALUES (?)",
                (document_id,),
            )
        else:
            connection.execute(
                "DELETE FROM tracked_documents WHERE document_id = ?",
                (document_id,),
            )
    return True


def get_document_outline(
    connection: sqlite3.Connection, document_id: int, limit: int = 40
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT heading, MIN(ordinal) AS ordinal
        FROM passages
        WHERE document_id = ?
          AND COALESCE(heading, '') <> ''
        GROUP BY heading
        ORDER BY ordinal ASC
        LIMIT ?
        """,
        (document_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def search_documents(
    connection: sqlite3.Connection,
    query: str,
    page: int,
    page_size: int,
    legal_type: str | None = None,
    year: int | None = None,
    issuer: str | None = None,
) -> dict:
    page = max(page, 1)
    offset = (page - 1) * page_size
    filters: list[str] = []
    filter_params: list[object] = []

    if legal_type:
        filters.append("d.legal_type = ?")
        filter_params.append(legal_type)
    if year:
        filters.append("d.year = ?")
        filter_params.append(year)
    if issuer:
        filters.append("LOWER(d.issuing_authority) LIKE LOWER(?)")
        filter_params.append(f"%{issuer.strip()}%")

    query = query.strip()
    if query:
        if looks_like_identifier_query(query):
            identifier_results = search_identifier_documents(
                connection=connection,
                query=query,
                page=page,
                page_size=page_size,
                filters=filters,
                filter_params=filter_params,
            )
            if identifier_results["total"]:
                return identifier_results

        fts_query = to_fts_query(query)
        if not fts_query:
            return {"items": [], "page": page, "page_count": 0, "total": 0}

        where_clause = (
            " AND ".join(["documents_fts MATCH ?", *filters])
            if filters
            else "documents_fts MATCH ?"
        )
        count_sql = f"""
            SELECT COUNT(*)
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE {where_clause}
        """
        total = connection.execute(count_sql, [fts_query, *filter_params]).fetchone()[0]
        if not total:
            return search_retrieval_documents(
                connection=connection,
                query=query,
                page=page,
                page_size=page_size,
                filters=filters,
                filter_params=filter_params,
            )

        sql = f"""
            SELECT
                d.id,
                d.document_number,
                d.title,
                d.legal_type,
                d.issuing_authority,
                d.issuance_date,
                d.legal_sectors,
                d.url,
                snippet(documents_fts, 2, '<mark>', '</mark>', ' ... ', 18) AS snippet,
                bm25(documents_fts, 5.0, 1.0, 2.0) AS rank
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE {where_clause}
            ORDER BY rank, d.year DESC, d.title ASC
            LIMIT ? OFFSET ?
        """
        rows = connection.execute(
            sql, [fts_query, *filter_params, page_size, offset]
        ).fetchall()
    else:
        where_clause = " AND ".join(filters) if filters else "1 = 1"
        count_sql = f"SELECT COUNT(*) FROM documents d WHERE {where_clause}"
        total = connection.execute(count_sql, filter_params).fetchone()[0]
        sql = f"""
            SELECT
                d.id,
                d.document_number,
                d.title,
                d.legal_type,
                d.issuing_authority,
                d.issuance_date,
                d.legal_sectors,
                d.url,
                d.excerpt AS snippet
            FROM documents d
            WHERE {where_clause}
            ORDER BY d.year DESC, d.issuance_date DESC, d.title ASC
            LIMIT ? OFFSET ?
        """
        rows = connection.execute(sql, [*filter_params, page_size, offset]).fetchall()

    page_count = (total + page_size - 1) // page_size if total else 0
    return {
        "items": [dict(row) for row in rows],
        "page": page,
        "page_count": page_count,
        "total": total,
    }


def get_document(connection: sqlite3.Connection, document_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT *
        FROM documents
        WHERE id = ?
        """,
        (document_id,),
    ).fetchone()
    return dict(row) if row else None


def get_documents_by_ids(
    connection: sqlite3.Connection, document_ids: list[int]
) -> list[dict]:
    if not document_ids:
        return []

    placeholders = ", ".join("?" for _ in document_ids)
    rows = connection.execute(
        f"""
        SELECT *
        FROM documents
        WHERE id IN ({placeholders})
        """,
        document_ids,
    ).fetchall()
    documents_by_id = {row["id"]: dict(row) for row in rows}
    return [
        documents_by_id[document_id]
        for document_id in document_ids
        if document_id in documents_by_id
    ]


def get_related_documents(
    connection: sqlite3.Connection, document: dict, limit: int = 4
) -> list[dict]:
    graph_rows = connection.execute(
        """
        SELECT DISTINCT d.id, d.title, d.document_number, d.legal_type, d.issuance_date
        FROM document_relations r
        JOIN documents d
          ON d.id = CASE
                WHEN r.source_document_id = ? THEN r.target_document_id
                ELSE r.source_document_id
            END
        WHERE r.source_document_id = ? OR r.target_document_id = ?
        ORDER BY d.year DESC, d.title ASC
        LIMIT ?
        """,
        (document["id"], document["id"], document["id"], limit),
    ).fetchall()
    related_by_id = {row["id"]: dict(row) for row in graph_rows}

    citation_rows = connection.execute(
        """
        SELECT DISTINCT d.id, d.title, d.document_number, d.legal_type, d.issuance_date
        FROM citation_links cl
        JOIN citation_mentions m ON m.id = cl.mention_id
        JOIN documents d
          ON d.id = CASE
                WHEN m.source_document_id = ? THEN cl.target_document_id
                ELSE m.source_document_id
            END
        WHERE m.source_document_id = ? OR cl.target_document_id = ?
        ORDER BY d.year DESC, d.title ASC
        LIMIT ?
        """,
        (document["id"], document["id"], document["id"], limit),
    ).fetchall()
    for row in citation_rows:
        related_by_id.setdefault(row["id"], dict(row))

    related = list(related_by_id.values())
    if len(related) >= limit:
        return related[:limit]

    excluded_ids = [document["id"], *[item["id"] for item in related]]
    placeholders = ", ".join("?" for _ in excluded_ids)
    fallback_rows = connection.execute(
        """
        SELECT id, title, document_number, legal_type, issuance_date
        FROM documents
        WHERE id NOT IN ("""
        + placeholders
        + """)
          AND (
                legal_type = ?
             OR issuing_authority = ?
             OR year = ?
          )
        ORDER BY ABS(COALESCE(year, 0) - COALESCE(?, 0)) ASC, title ASC
        LIMIT ?
        """,
        (
            *excluded_ids,
            document.get("legal_type") or "",
            document.get("issuing_authority") or "",
            document.get("year"),
            document.get("year"),
            limit - len(related),
        ),
    ).fetchall()
    return [*related, *[dict(row) for row in fallback_rows]]


def retrieve_passages(
    connection: sqlite3.Connection,
    query: str,
    limit: int,
    document_id: int | None = None,
) -> list[dict]:
    fts_query = to_fts_query(query)
    if not fts_query:
        return []

    filters = ["passages_fts MATCH ?"]
    params: list[object] = [fts_query]
    if document_id is not None:
        filters.append("p.document_id = ?")
        params.append(document_id)
        document_rank_map: dict[int, int] = {}
        document_results = {"items": []}
    else:
        focus_query = build_focus_query(query)
        document_results = search_documents(
            connection=connection,
            query=focus_query,
            page=1,
            page_size=max(limit * 4, 12),
        )
        document_rank_map = {
            int(item["id"]): index
            for index, item in enumerate(document_results["items"])
        }
        candidate_ids = [item["id"] for item in document_results["items"]]
        if len(candidate_ids) < 24:
            retrieval_ids = retrieve_candidate_document_ids(
                connection, focus_query, limit=48
            )
            seen_ids = set(candidate_ids)
            candidate_ids.extend(item for item in retrieval_ids if item not in seen_ids)
        if candidate_ids:
            placeholders = ", ".join("?" for _ in candidate_ids)
            filters.append(f"p.document_id IN ({placeholders})")
            params.extend(candidate_ids)

    fetch_limit = max(limit * 12, 24)

    sql = f"""
        SELECT
            p.id,
            p.document_id,
            p.ordinal,
            p.heading,
            p.text,
            d.title,
            d.document_number,
            d.legal_type,
            d.issuing_authority,
            d.issuance_date,
            d.url,
            bm25(passages_fts, 1.5, 1.0) AS rank
        FROM passages_fts
        JOIN passages p ON p.id = passages_fts.rowid
        JOIN documents d ON d.id = p.document_id
        WHERE {" AND ".join(filters)}
        ORDER BY rank, d.year DESC
        LIMIT ?
    """
    rows = [
        dict(row) for row in connection.execute(sql, [*params, fetch_limit]).fetchall()
    ]
    rows.extend(build_overview_passages(document_results))
    return rerank_passages(
        query,
        rows,
        limit,
        document_rank_map=document_rank_map,
    )

from __future__ import annotations

import re
import sqlite3
from datetime import datetime


TOKEN_PATTERN = re.compile(r"[0-9A-Za-zÀ-ỹ]+", re.UNICODE)


def to_fts_query(raw_query: str) -> str:
    tokens = [token for token in TOKEN_PATTERN.findall(raw_query) if len(token) >= 2]
    if not tokens:
        return ""
    return " AND ".join(f'"{token}"*' for token in tokens[:10])


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
    rows = connection.execute(sql, [*params, limit]).fetchall()
    return [dict(row) for row in rows]

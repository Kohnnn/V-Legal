from __future__ import annotations

import sqlite3
from urllib.parse import urlencode


def build_default_view_name(
    query: str,
    topic_name: str | None,
    legal_type: str | None,
) -> str:
    if query.strip():
        return f"Research: {query.strip()[:48]}"
    if topic_name:
        return f"Topic watch: {topic_name}"
    if legal_type:
        return f"{legal_type} watch"
    return "Saved legal view"


def list_research_views(connection: sqlite3.Connection, limit: int = 12) -> list[dict]:
    rows = connection.execute(
        """
        SELECT id, name, query, topic_slug, legal_type, year, issuer, created_at, updated_at
        FROM research_views
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_research_view(connection: sqlite3.Connection, view_id: int) -> dict | None:
    row = connection.execute(
        """
        SELECT id, name, query, topic_slug, legal_type, year, issuer, created_at, updated_at
        FROM research_views
        WHERE id = ?
        """,
        (view_id,),
    ).fetchone()
    return dict(row) if row else None


def create_research_view(
    connection: sqlite3.Connection,
    *,
    name: str,
    query: str,
    topic_slug: str | None,
    legal_type: str | None,
    year: int | None,
    issuer: str | None,
) -> int:
    with connection:
        cursor = connection.execute(
            """
            INSERT INTO research_views (name, query, topic_slug, legal_type, year, issuer)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                query.strip(),
                topic_slug.strip() if topic_slug else None,
                legal_type.strip() if legal_type else None,
                year,
                issuer.strip() if issuer else None,
            ),
        )
    return int(cursor.lastrowid)


def delete_research_view(connection: sqlite3.Connection, view_id: int) -> None:
    with connection:
        connection.execute("DELETE FROM research_views WHERE id = ?", (view_id,))


def build_research_query_string(view: dict) -> str:
    params = {
        "q": view.get("query") or "",
        "topic": view.get("topic_slug") or "",
        "legal_type": view.get("legal_type") or "",
        "year": view.get("year") or "",
        "issuer": view.get("issuer") or "",
    }
    return urlencode(params)

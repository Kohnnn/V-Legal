from __future__ import annotations

from datetime import datetime
from typing import Any

from appwrite.client import Client
from appwrite.id import ID
from appwrite.query import Query
from appwrite.services.tables_db import TablesDB

from .settings import get_settings


def get_appwrite_client() -> Client:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return client


def get_tables_db() -> TablesDB:
    return TablesDB(get_appwrite_client())


def _row_to_dict(row) -> dict[str, Any]:
    base = {
        "id": row.id,
        "$id": row.id,
        "created_at": getattr(row, "createdat", None),
        "updated_at": getattr(row, "updatedat", None),
    }
    if hasattr(row, "data") and row.data:
        base.update(row.data)
    return base


TRACKED_COLLECTION = "tracked_documents"
RESEARCH_COLLECTION = "research_views"


def aw_list_tracked(user_id: str) -> list[dict[str, Any]]:
    settings = get_settings()
    tdb = get_tables_db()
    result = tdb.list_rows(
        database_id=settings.appwrite_database_id,
        table_id=TRACKED_COLLECTION,
        queries=[Query.equal("user_id", user_id)],
    )
    return [_row_to_dict(d) for d in result.rows]


def aw_track_document(
    user_id: str,
    document_id: int,
    document_title: str,
    document_number: str,
) -> dict[str, Any]:
    settings = get_settings()
    tdb = get_tables_db()
    existing = tdb.list_rows(
        database_id=settings.appwrite_database_id,
        table_id=TRACKED_COLLECTION,
        queries=[
            Query.equal("user_id", user_id),
            Query.equal("document_id", document_id),
        ],
    )
    if existing.rows:
        return _row_to_dict(existing.rows[0])

    doc = tdb.create_row(
        database_id=settings.appwrite_database_id,
        table_id=TRACKED_COLLECTION,
        row_id=ID.unique(),
        data={
            "user_id": user_id,
            "document_id": document_id,
            "document_title": document_title,
            "document_number": document_number,
            "tracked_at": datetime.utcnow().isoformat(),
        },
    )
    return _row_to_dict(doc)


def aw_untrack_document(user_id: str, document_id: int) -> None:
    settings = get_settings()
    tdb = get_tables_db()
    existing = tdb.list_rows(
        database_id=settings.appwrite_database_id,
        table_id=TRACKED_COLLECTION,
        queries=[
            Query.equal("user_id", user_id),
            Query.equal("document_id", document_id),
        ],
    )
    for d in existing.rows:
        tdb.delete_row(
            database_id=settings.appwrite_database_id,
            table_id=TRACKED_COLLECTION,
            row_id=d.id,
        )


def aw_list_research_views(user_id: str) -> list[dict[str, Any]]:
    settings = get_settings()
    tdb = get_tables_db()
    result = tdb.list_rows(
        database_id=settings.appwrite_database_id,
        table_id=RESEARCH_COLLECTION,
        queries=[Query.equal("user_id", user_id)],
    )
    return [_row_to_dict(d) for d in result.rows]


def aw_get_research_view(user_id: str, view_id: str) -> dict[str, Any] | None:
    settings = get_settings()
    tdb = get_tables_db()
    try:
        doc = tdb.get_row(
            database_id=settings.appwrite_database_id,
            table_id=RESEARCH_COLLECTION,
            row_id=view_id,
        )
        d = _row_to_dict(doc)
        if d.get("user_id") != user_id:
            return None
        return d
    except Exception:
        return None


def aw_create_research_view(
    user_id: str,
    name: str,
    query: str,
    topic_slug: str,
    legal_type: str,
    year: int,
    issuer: str,
) -> dict[str, Any]:
    settings = get_settings()
    tdb = get_tables_db()
    doc = tdb.create_row(
        database_id=settings.appwrite_database_id,
        table_id=RESEARCH_COLLECTION,
        row_id=ID.unique(),
        data={
            "user_id": user_id,
            "name": name,
            "query": query,
            "topic_slug": topic_slug or "",
            "legal_type": legal_type or "",
            "year": year or 0,
            "issuer": issuer or "",
            "created_at": datetime.utcnow().isoformat(),
        },
    )
    return _row_to_dict(doc)


def aw_delete_research_view(user_id: str, view_id: str) -> bool:
    settings = get_settings()
    tdb = get_tables_db()
    try:
        doc = tdb.get_row(
            database_id=settings.appwrite_database_id,
            table_id=RESEARCH_COLLECTION,
            row_id=view_id,
        )
        d = _row_to_dict(doc)
        if d.get("user_id") != user_id:
            return False
        tdb.delete_row(
            database_id=settings.appwrite_database_id,
            table_id=RESEARCH_COLLECTION,
            row_id=view_id,
        )
        return True
    except Exception:
        return False

from __future__ import annotations

import argparse
import sqlite3

from appwrite.client import Client
from appwrite.query import Query
from appwrite.services.tables_db import TablesDB

from vlegal_prototype.settings import BASE_DIR, get_settings


CORPUS_TABLES_TO_CLEAR = [
    "documents",
    "passages",
    "taxonomy_subjects",
    "document_subjects",
    "document_relations",
    "document_sections",
    "citation_mentions",
    "citation_links",
]
DOCUMENT_EXTRA_COLUMNS = {
    "canonical_id": ("string", {"size": 255, "required": False}),
    "source_system": ("string", {"size": 64, "required": False}),
    "text_source": ("string", {"size": 32, "required": False}),
    "parse_confidence": ("string", {"size": 16, "required": False}),
    "content_truncated": ("boolean", {"required": False, "default": False}),
}
REMOTE_CONTENT_LIMIT = 8000
REMOTE_PLAIN_LIMIT = 8000
STRING_LIMITS = {
    "canonical_id": 255,
    "document_number": 255,
    "title": 1000,
    "url": 2048,
    "legal_type": 255,
    "legal_sectors": 500,
    "issuing_authority": 500,
    "issuance_date": 50,
    "signers": 1000,
    "excerpt": 1000,
    "source": 2048,
    "source_system": 64,
    "text_source": 32,
    "parse_confidence": 16,
}


def get_tablesdb() -> TablesDB:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return TablesDB(client)


def list_existing_columns(tdb: TablesDB, database_id: str, table_id: str) -> set[str]:
    result = tdb.list_columns(database_id=database_id, table_id=table_id)
    columns = result["columns"] if isinstance(result, dict) else result.columns
    return {column["key"] if isinstance(column, dict) else column.key for column in columns}


def ensure_documents_columns(tdb: TablesDB, database_id: str) -> None:
    existing = list_existing_columns(tdb, database_id, "documents")
    for key, (column_type, kwargs) in DOCUMENT_EXTRA_COLUMNS.items():
        if key in existing:
            continue
        if column_type == "string":
            tdb.create_string_column(
                database_id=database_id,
                table_id="documents",
                key=key,
                size=kwargs["size"],
                required=kwargs.get("required", False),
            )
        elif column_type == "boolean":
            tdb.create_boolean_column(
                database_id=database_id,
                table_id="documents",
                key=key,
                required=kwargs.get("required", False),
                default=kwargs.get("default", False),
            )
        print(f"Added documents column '{key}'")


def clear_table_rows(tdb: TablesDB, database_id: str, table_id: str) -> None:
    try:
        tdb.delete_rows(database_id=database_id, table_id=table_id)
        print(f"Cleared table '{table_id}'")
    except Exception as exc:
        print(f"Skip clearing '{table_id}': {exc}")


def build_remote_document_row(row: sqlite3.Row) -> dict:
    def fit(key: str, value: str | None) -> str:
        text = value or ""
        limit = STRING_LIMITS.get(key)
        if limit and len(text) > limit:
            return text[:limit]
        return text

    content = row["content"] or ""
    plain_content = row["plain_content"] or ""
    return {
        "canonical_id": fit("canonical_id", row["canonical_id"]),
        "document_number": fit("document_number", row["document_number"]),
        "title": fit("title", row["title"]),
        "url": fit("url", row["url"]),
        "legal_type": fit("legal_type", row["legal_type"]),
        "legal_sectors": fit("legal_sectors", row["legal_sectors"]),
        "issuing_authority": fit("issuing_authority", row["issuing_authority"]),
        "issuance_date": fit("issuance_date", row["issuance_date"]),
        "signers": fit("signers", row["signers"]),
        "content": content[:REMOTE_CONTENT_LIMIT],
        "plain_content": plain_content[:REMOTE_PLAIN_LIMIT],
        "excerpt": fit("excerpt", row["excerpt"]),
        "year": row["year"] or 0,
        "source": fit("source", row["source"]),
        "imported_at": row["imported_at"],
        "source_system": fit("source_system", row["source_system"]),
        "text_source": fit("text_source", row["text_source"]),
        "parse_confidence": fit("parse_confidence", row["parse_confidence"]),
        "content_truncated": len(content) > REMOTE_CONTENT_LIMIT
        or len(plain_content) > REMOTE_PLAIN_LIMIT,
    }


def iter_sqlite_document_rows(sqlite_path: str):
    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    try:
        for row in connection.execute(
            "SELECT * FROM documents ORDER BY id"
        ):
            yield row
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear old Appwrite corpus rows and repopulate the documents table from the local SQLite corpus."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Rows per Appwrite bulk request. Free plan safe default is 100.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many local documents to upload.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip this many local SQLite documents before uploading. Useful for resume.",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear remote corpus tables before uploading. Useful for resume.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    if not settings.appwrite_project_id or not settings.appwrite_database_id or not settings.appwrite_api_key:
        raise SystemExit("Resolved Appwrite configuration is incomplete.")

    tdb = get_tablesdb()
    database_id = settings.appwrite_database_id
    sqlite_path = BASE_DIR / "data" / "corpus" / "sqlite" / "vlegal.sqlite"
    ensure_documents_columns(tdb, database_id)

    if not args.no_clear:
        for table_id in CORPUS_TABLES_TO_CLEAR:
            clear_table_rows(tdb, database_id, table_id)

    uploaded = 0
    batch: list[dict] = []
    for index, row in enumerate(iter_sqlite_document_rows(str(sqlite_path))):
        if index < args.offset:
            continue
        batch.append(build_remote_document_row(row))
        if args.limit and uploaded + len(batch) >= args.limit:
            batch = batch[: max(0, args.limit - uploaded)]
        if len(batch) < args.batch_size and not (args.limit and uploaded + len(batch) >= args.limit):
            continue
        result = tdb.create_rows(database_id=database_id, table_id="documents", rows=batch)
        rows = result["rows"] if isinstance(result, dict) else result.rows
        uploaded += len(rows)
        print(f"Uploaded {uploaded} Appwrite documents...")
        batch.clear()
        if args.limit and uploaded >= args.limit:
            break

    if batch:
        result = tdb.create_rows(database_id=database_id, table_id="documents", rows=batch)
        rows = result["rows"] if isinstance(result, dict) else result.rows
        uploaded += len(rows)

    print(f"Done. Uploaded {uploaded} documents to Appwrite table 'documents'.")


if __name__ == "__main__":
    main()

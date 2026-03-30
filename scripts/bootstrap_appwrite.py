from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from appwrite.client import Client
from appwrite.services.tables_db import TablesDB
from appwrite.enums.tables_db_index_type import TablesDBIndexType

from vlegal_prototype.settings import get_settings


COLUMNS = {
    "documents": [
        {"key": "document_number", "type": "varchar", "size": 255, "required": False},
        {"key": "title", "type": "varchar", "size": 1000, "required": True},
        {"key": "url", "type": "varchar", "size": 2048, "required": False},
        {"key": "legal_type", "type": "varchar", "size": 255, "required": False},
        {"key": "legal_sectors", "type": "varchar", "size": 500, "required": False},
        {"key": "issuing_authority", "type": "varchar", "size": 500, "required": False},
        {"key": "issuance_date", "type": "varchar", "size": 50, "required": False},
        {"key": "signers", "type": "varchar", "size": 1000, "required": False},
        {"key": "content", "type": "longtext", "required": True},
        {"key": "plain_content", "type": "longtext", "required": True},
        {"key": "excerpt", "type": "varchar", "size": 1000, "required": False},
        {"key": "year", "type": "integer", "required": False},
        {"key": "source", "type": "varchar", "size": 2048, "required": True},
        {"key": "imported_at", "type": "datetime", "required": False},
    ],
    "passages": [
        {"key": "document_id", "type": "integer", "required": True},
        {"key": "ordinal", "type": "integer", "required": True},
        {"key": "heading", "type": "varchar", "size": 500, "required": False},
        {"key": "text", "type": "longtext", "required": True},
    ],
    "tracked_documents": [
        {"key": "document_id", "type": "integer", "required": True},
        {"key": "tracked_at", "type": "datetime", "required": False},
    ],
    "taxonomy_subjects": [
        {"key": "name", "type": "varchar", "size": 500, "required": True},
        {"key": "slug", "type": "varchar", "size": 255, "required": True},
        {"key": "source", "type": "varchar", "size": 100, "required": True},
        {"key": "source_url", "type": "varchar", "size": 2048, "required": False},
        {"key": "imported_at", "type": "datetime", "required": False},
    ],
    "document_subjects": [
        {"key": "document_id", "type": "integer", "required": True},
        {"key": "subject_id", "type": "varchar", "size": 100, "required": True},
    ],
    "document_relations": [
        {"key": "source_document_id", "type": "integer", "required": True},
        {"key": "target_document_id", "type": "integer", "required": True},
        {"key": "relation_type", "type": "varchar", "size": 50, "required": True},
        {"key": "evidence_text", "type": "varchar", "size": 2000, "required": False},
        {"key": "confidence", "type": "varchar", "size": 20, "required": True},
        {"key": "created_at", "type": "datetime", "required": False},
    ],
    "document_sections": [
        {"key": "document_id", "type": "integer", "required": True},
        {"key": "ordinal", "type": "integer", "required": True},
        {"key": "section_type", "type": "varchar", "size": 50, "required": True},
        {"key": "label", "type": "varchar", "size": 500, "required": True},
        {"key": "anchor", "type": "varchar", "size": 255, "required": True},
        {"key": "text", "type": "longtext", "required": True},
    ],
    "citation_mentions": [
        {"key": "source_document_id", "type": "integer", "required": True},
        {"key": "source_section_id", "type": "integer", "required": True},
        {"key": "mention_order", "type": "integer", "required": True},
        {"key": "raw_reference", "type": "varchar", "size": 1000, "required": True},
        {"key": "referenced_number", "type": "varchar", "size": 255, "required": False},
        {"key": "referenced_label", "type": "varchar", "size": 500, "required": False},
        {"key": "cue_phrase", "type": "varchar", "size": 500, "required": False},
        {"key": "mention_type", "type": "varchar", "size": 50, "required": True},
        {"key": "confidence", "type": "varchar", "size": 20, "required": True},
        {"key": "created_at", "type": "datetime", "required": False},
    ],
    "citation_links": [
        {"key": "mention_id", "type": "integer", "required": True},
        {"key": "target_document_id", "type": "integer", "required": True},
        {"key": "target_section_id", "type": "integer", "required": False},
        {"key": "link_type", "type": "varchar", "size": 50, "required": True},
        {"key": "score", "type": "double", "required": True},
        {"key": "match_method", "type": "varchar", "size": 50, "required": True},
    ],
    "research_views": [
        {"key": "name", "type": "varchar", "size": 500, "required": True},
        {"key": "query", "type": "varchar", "size": 2000, "required": True},
        {"key": "topic_slug", "type": "varchar", "size": 255, "required": False},
        {"key": "legal_type", "type": "varchar", "size": 255, "required": False},
        {"key": "year", "type": "integer", "required": False},
        {"key": "issuer", "type": "varchar", "size": 500, "required": False},
        {"key": "created_at", "type": "datetime", "required": False},
        {"key": "updated_at", "type": "datetime", "required": False},
    ],
}

INDEXES = {
    "documents": [
        {
            "key": "idx_doc_legal_type",
            "type": TablesDBIndexType.KEY,
            "columns": ["legal_type"],
        },
        {"key": "idx_doc_year", "type": TablesDBIndexType.KEY, "columns": ["year"]},
        {
            "key": "idx_doc_issuer",
            "type": TablesDBIndexType.KEY,
            "columns": ["issuing_authority"],
        },
    ],
    "passages": [
        {
            "key": "idx_passage_doc",
            "type": TablesDBIndexType.KEY,
            "columns": ["document_id"],
        },
    ],
    "tracked_documents": [
        {
            "key": "idx_tracked_doc_id",
            "type": TablesDBIndexType.KEY,
            "columns": ["document_id"],
        },
    ],
    "taxonomy_subjects": [
        {
            "key": "idx_taxonomy_slug",
            "type": TablesDBIndexType.KEY,
            "columns": ["slug"],
            "unique": True,
        },
    ],
    "document_subjects": [
        {
            "key": "idx_docsubj_doc",
            "type": TablesDBIndexType.KEY,
            "columns": ["document_id"],
        },
        {
            "key": "idx_docsubj_subject",
            "type": TablesDBIndexType.KEY,
            "columns": ["subject_id"],
        },
    ],
    "document_relations": [
        {
            "key": "idx_rel_source",
            "type": TablesDBIndexType.KEY,
            "columns": ["source_document_id", "relation_type"],
        },
        {
            "key": "idx_rel_target",
            "type": TablesDBIndexType.KEY,
            "columns": ["target_document_id"],
        },
    ],
    "document_sections": [
        {
            "key": "idx_docsect_doc",
            "type": TablesDBIndexType.KEY,
            "columns": ["document_id", "ordinal"],
        },
    ],
    "citation_mentions": [
        {
            "key": "idx_citment_src",
            "type": TablesDBIndexType.KEY,
            "columns": ["source_document_id", "source_section_id"],
        },
    ],
    "citation_links": [
        {
            "key": "idx_citlink_target",
            "type": TablesDBIndexType.KEY,
            "columns": ["target_document_id", "link_type"],
        },
    ],
    "research_views": [
        {
            "key": "idx_resview_created",
            "type": TablesDBIndexType.KEY,
            "columns": ["created_at"],
        },
    ],
}

COLUMN_METHODS = {
    "varchar": "create_varchar_column",
    "string": "create_varchar_column",
    "text": "create_text_column",
    "mediumtext": "create_mediumtext_column",
    "longtext": "create_longtext_column",
    "integer": "create_integer_column",
    "double": "create_float_column",
    "float": "create_float_column",
    "datetime": "create_datetime_column",
    "boolean": "create_boolean_column",
}


def get_tablesdb() -> TablesDB:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return TablesDB(client)


def create_tables(tdb: TablesDB) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id

    try:
        existing = tdb.list_tables(database_id=db_id)
        existing_ids = {t["$id"] for t in existing.tables}
    except Exception:
        existing_ids = set()

    for table_id in COLUMNS:
        if table_id in existing_ids:
            print(f"Table '{table_id}' already exists, skipping")
            continue

        tdb.create_table(database_id=db_id, table_id=table_id, name=table_id)
        print(f"Created table '{table_id}'")


def add_columns(tdb: TablesDB) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id

    for table_id, cols in COLUMNS.items():
        for col in cols:
            col_type = col["type"]
            col_key = col["key"]
            method_name = COLUMN_METHODS.get(col_type)
            if not method_name:
                print(f"  Unknown type '{col_type}' for '{col_key}', skipping")
                continue

            method = getattr(tdb, method_name)
            try:
                if col_type == "varchar":
                    method(
                        database_id=db_id,
                        table_id=table_id,
                        key=col_key,
                        size=col.get("size", 255),
                        required=col.get("required", False),
                    )
                elif col_type in (
                    "integer",
                    "datetime",
                    "boolean",
                    "text",
                    "mediumtext",
                    "longtext",
                    "double",
                    "float",
                ):
                    method(
                        database_id=db_id,
                        table_id=table_id,
                        key=col_key,
                        required=col.get("required", False),
                    )
                print(f"  Added column '{col_key}' ({col_type})")
            except Exception as e:
                print(f"  Column '{col_key}': {e}")


def add_indexes(tdb: TablesDB) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id

    for table_id, indexes in INDEXES.items():
        for idx in indexes:
            idx_key = idx["key"]
            idx_type = idx["type"]
            idx_columns = idx["columns"]
            idx_unique = idx.get("unique", False)
            try:
                tdb.create_index(
                    database_id=db_id,
                    table_id=table_id,
                    key=idx_key,
                    type=idx_type,
                    columns=idx_columns,
                )
                print(f"  Added index '{idx_key}' on {idx_columns}")
            except Exception as e:
                print(f"  Index '{idx_key}': {e}")


def main() -> None:
    settings = get_settings()
    if not settings.appwrite_api_key:
        print("ERROR: VLEGAL_APPWRITE_API_KEY not set")
        sys.exit(1)

    print(f"Appwrite endpoint: {settings.appwrite_endpoint}")
    print(f"Project ID: {settings.appwrite_project_id}")
    print(f"Database ID: {settings.appwrite_database_id}")
    print()

    tdb = get_tablesdb()

    print("[1/3] Creating tables...")
    create_tables(tdb)

    print("\n[2/3] Adding columns...")
    add_columns(tdb)

    print("\n[3/3] Creating indexes...")
    add_indexes(tdb)

    print("\nDone. Appwrite schema is ready.")
    print(
        "NOTE: Full-text search on 'content'/'text' columns is not available in Appwrite."
    )
    print(
        "      The app uses Appwrite for storage only; search is handled differently."
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv
from appwrite.client import Client
from appwrite.query import Query

load_dotenv()

from vlegal_prototype.settings import get_settings

COLLECTIONS = [
    {
        "$id": "documents",
        "name": "documents",
        "attributes": [
            {
                "key": "document_number",
                "type": "string",
                "size": 255,
                "required": False,
            },
            {"key": "title", "type": "string", "size": 1000, "required": True},
            {"key": "url", "type": "string", "size": 2048, "required": False},
            {"key": "legal_type", "type": "string", "size": 255, "required": False},
            {"key": "legal_sectors", "type": "string", "size": 500, "required": False},
            {
                "key": "issuing_authority",
                "type": "string",
                "size": 500,
                "required": False,
            },
            {"key": "issuance_date", "type": "string", "size": 50, "required": False},
            {"key": "signers", "type": "string", "size": 1000, "required": False},
            {"key": "content", "type": "string", "size": 16777216, "required": True},
            {
                "key": "plain_content",
                "type": "string",
                "size": 16777216,
                "required": True,
            },
            {"key": "excerpt", "type": "string", "size": 1000, "required": False},
            {"key": "year", "type": "integer", "required": False},
            {"key": "source", "type": "string", "size": 2048, "required": True},
            {"key": "imported_at", "type": "datetime", "required": False},
        ],
        "indexes": [
            {"key": "idx_doc_legal_type", "type": "key", "attributes": ["legal_type"]},
            {"key": "idx_doc_year", "type": "key", "attributes": ["year"]},
            {
                "key": "idx_doc_issuer",
                "type": "key",
                "attributes": ["issuing_authority"],
            },
        ],
    },
    {
        "$id": "passages",
        "name": "passages",
        "attributes": [
            {"key": "document_id", "type": "integer", "required": True},
            {"key": "ordinal", "type": "integer", "required": True},
            {"key": "heading", "type": "string", "size": 500, "required": False},
            {"key": "text", "type": "string", "size": 16777216, "required": True},
        ],
        "indexes": [
            {"key": "idx_passage_doc", "type": "key", "attributes": ["document_id"]},
        ],
    },
    {
        "$id": "tracked_documents",
        "name": "tracked_documents",
        "attributes": [
            {"key": "document_id", "type": "integer", "required": True},
            {"key": "tracked_at", "type": "datetime", "required": False},
        ],
        "indexes": [
            {"key": "idx_tracked_doc_id", "type": "key", "attributes": ["document_id"]},
        ],
    },
    {
        "$id": "taxonomy_subjects",
        "name": "taxonomy_subjects",
        "attributes": [
            {"key": "name", "type": "string", "size": 500, "required": True},
            {"key": "slug", "type": "string", "size": 255, "required": True},
            {"key": "source", "type": "string", "size": 100, "required": True},
            {"key": "source_url", "type": "string", "size": 2048, "required": False},
            {"key": "imported_at", "type": "datetime", "required": False},
        ],
        "indexes": [
            {
                "key": "idx_taxonomy_slug",
                "type": "key",
                "attributes": ["slug"],
                "unique": True,
            },
        ],
    },
    {
        "$id": "document_subjects",
        "name": "document_subjects",
        "attributes": [
            {"key": "document_id", "type": "integer", "required": True},
            {"key": "subject_id", "type": "string", "size": 100, "required": True},
        ],
        "indexes": [
            {"key": "idx_docsubj_doc", "type": "key", "attributes": ["document_id"]},
            {"key": "idx_docsubj_subject", "type": "key", "attributes": ["subject_id"]},
        ],
    },
    {
        "$id": "document_relations",
        "name": "document_relations",
        "attributes": [
            {"key": "source_document_id", "type": "integer", "required": True},
            {"key": "target_document_id", "type": "integer", "required": True},
            {"key": "relation_type", "type": "string", "size": 50, "required": True},
            {"key": "evidence_text", "type": "string", "size": 2000, "required": False},
            {"key": "confidence", "type": "string", "size": 20, "required": True},
            {"key": "created_at", "type": "datetime", "required": False},
        ],
        "indexes": [
            {
                "key": "idx_rel_source",
                "type": "key",
                "attributes": ["source_document_id", "relation_type"],
            },
            {
                "key": "idx_rel_target",
                "type": "key",
                "attributes": ["target_document_id"],
            },
        ],
    },
    {
        "$id": "document_sections",
        "name": "document_sections",
        "attributes": [
            {"key": "document_id", "type": "integer", "required": True},
            {"key": "ordinal", "type": "integer", "required": True},
            {"key": "section_type", "type": "string", "size": 50, "required": True},
            {"key": "label", "type": "string", "size": 500, "required": True},
            {"key": "anchor", "type": "string", "size": 255, "required": True},
            {"key": "text", "type": "string", "size": 16777216, "required": True},
        ],
        "indexes": [
            {
                "key": "idx_docsect_doc",
                "type": "key",
                "attributes": ["document_id", "ordinal"],
            },
        ],
    },
    {
        "$id": "citation_mentions",
        "name": "citation_mentions",
        "attributes": [
            {"key": "source_document_id", "type": "integer", "required": True},
            {"key": "source_section_id", "type": "integer", "required": True},
            {"key": "mention_order", "type": "integer", "required": True},
            {"key": "raw_reference", "type": "string", "size": 1000, "required": True},
            {
                "key": "referenced_number",
                "type": "string",
                "size": 255,
                "required": False,
            },
            {
                "key": "referenced_label",
                "type": "string",
                "size": 500,
                "required": False,
            },
            {"key": "cue_phrase", "type": "string", "size": 500, "required": False},
            {"key": "mention_type", "type": "string", "size": 50, "required": True},
            {"key": "confidence", "type": "string", "size": 20, "required": True},
            {"key": "created_at", "type": "datetime", "required": False},
        ],
        "indexes": [
            {
                "key": "idx_citment_src",
                "type": "key",
                "attributes": ["source_document_id", "source_section_id"],
            },
        ],
    },
    {
        "$id": "citation_links",
        "name": "citation_links",
        "attributes": [
            {"key": "mention_id", "type": "integer", "required": True},
            {"key": "target_document_id", "type": "integer", "required": True},
            {"key": "target_section_id", "type": "integer", "required": False},
            {"key": "link_type", "type": "string", "size": 50, "required": True},
            {"key": "score", "type": "double", "required": True},
            {"key": "match_method", "type": "string", "size": 50, "required": True},
        ],
        "indexes": [
            {
                "key": "idx_citlink_target",
                "type": "key",
                "attributes": ["target_document_id", "link_type"],
            },
        ],
    },
    {
        "$id": "research_views",
        "name": "research_views",
        "attributes": [
            {"key": "name", "type": "string", "size": 500, "required": True},
            {"key": "query", "type": "string", "size": 2000, "required": True},
            {"key": "topic_slug", "type": "string", "size": 255, "required": False},
            {"key": "legal_type", "type": "string", "size": 255, "required": False},
            {"key": "year", "type": "integer", "required": False},
            {"key": "issuer", "type": "string", "size": 500, "required": False},
            {"key": "created_at", "type": "datetime", "required": False},
            {"key": "updated_at", "type": "datetime", "required": False},
        ],
        "indexes": [
            {"key": "idx_resview_created", "type": "key", "attributes": ["created_at"]},
        ],
    },
]


def get_client() -> Client:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return client


def create_database(client: Client) -> None:
    settings = get_settings()
    try:
        client.databases.create(
            database_id=settings.appwrite_database_id,
            name="vlegal",
        )
        print(f"Created database '{settings.appwrite_database_id}'")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"Database '{settings.appwrite_database_id}' already exists")
        else:
            raise


def create_collections(client: Client) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id
    existing = set()
    try:
        cols = client.databases.list_collections(db_id)
        existing = {c["$id"] for c in cols.get("collections", [])}
    except Exception:
        pass

    for col_def in COLLECTIONS:
        col_id = col_def["$id"]
        if col_id in existing:
            print(f"Collection '{col_id}' already exists, skipping")
            continue

        attributes = col_def.pop("attributes")
        indexes = col_def.pop("indexes")

        client.databases.create_collection(
            database_id=db_id,
            name=col_def["name"],
            **col_def,
        )
        print(f"Created collection '{col_id}'")

        for attr in attributes:
            try:
                client.databases.create_attribute(
                    database_id=db_id,
                    collection_id=col_id,
                    **attr,
                )
            except Exception as e:
                print(f"  attr {attr['key']}: {e}")

        for idx in indexes:
            try:
                client.databases.create_index(
                    database_id=db_id,
                    collection_id=col_id,
                    **idx,
                )
            except Exception as e:
                print(f"  index {idx['key']}: {e}")


def main() -> None:
    client = get_client()
    create_database(client)
    create_collections(client)
    print("Done. Appwrite schema is ready.")


if __name__ == "__main__":
    main()

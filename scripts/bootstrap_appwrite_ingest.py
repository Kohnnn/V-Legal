from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datetime import datetime
import time

from dotenv import load_dotenv

load_dotenv()

from appwrite.client import Client
from appwrite.query import Query

from vlegal_prototype.settings import get_settings
from vlegal_prototype.hf_ingest import stream_hf_records, split_into_passages


BATCH_SIZE = 100


def get_client() -> Client:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return client


def create_document(client: Client, record: dict) -> str:
    settings = get_settings()
    db_id = settings.appwrite_database_id

    doc = client.databases.create_document(
        database_id=db_id,
        collection_id="documents",
        document_id=str(record["id"]),
        data={
            "document_number": record.get("document_number") or "",
            "title": record["title"],
            "url": record.get("url") or "",
            "legal_type": record.get("legal_type") or "",
            "legal_sectors": record.get("legal_sectors") or "",
            "issuing_authority": record.get("issuing_authority") or "",
            "issuance_date": record.get("issuance_date") or "",
            "signers": record.get("signers") or "",
            "content": record["content"],
            "plain_content": record["plain_content"],
            "excerpt": record.get("excerpt") or "",
            "year": record.get("year"),
            "source": record["source"],
            "imported_at": datetime.utcnow().isoformat(),
        },
    )
    return doc["$id"]


def create_passages(client: Client, document_id: int, passages: list[dict]) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id

    for p in passages:
        client.databases.create_document(
            database_id=db_id,
            collection_id="passages",
            document_id="unique()",
            data={
                "document_id": document_id,
                "ordinal": p["ordinal"],
                "heading": p.get("heading") or "",
                "text": p["text"],
            },
        )


def clear_passages(client: Client, document_id: int) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id
    result = client.databases.list_documents(
        database_id=db_id,
        collection_id="passages",
        queries=[Query.equal("document_id", document_id)],
    )
    for doc in result.get("documents", []):
        client.databases.delete_document(
            database_id=db_id,
            collection_id="passages",
            document_id=doc["$id"],
        )


def main() -> None:
    settings = get_settings()
    if not settings.appwrite_api_key:
        print("ERROR: APPWRITE_API_KEY not set in environment")
        sys.exit(1)

    client = get_client()
    db_id = settings.appwrite_database_id

    print(f"Streaming all records from {settings.dataset_name} into Appwrite...")

    imported = 0
    failed = 0

    for record in stream_hf_records(limit=None, skip=0):
        doc_id = record["id"]

        for attempt in range(3):
            try:
                create_document(client, record)
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                    continue
                raise

        try:
            clear_passages(client, doc_id)
            if record["passages"]:
                create_passages(client, doc_id, record["passages"])
        except Exception as e:
            print(f"  passages error for doc {doc_id}: {e}")

        imported += 1
        if imported % 500 == 0:
            print(f"Imported {imported} documents...")

        if imported % 1000 == 0:
            print(f"  sleeping 1s to avoid Appwrite rate limits...")
            time.sleep(1)

    print(
        f"Done. Imported {imported} documents ({failed} failed) into Appwrite DB '{db_id}'."
    )


if __name__ == "__main__":
    main()

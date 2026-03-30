from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

from vlegal_prototype.settings import get_settings
from vlegal_prototype.hf_ingest import stream_hf_records


BATCH_SIZE = 100


def get_db() -> Databases:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return Databases(client)


def create_document(db: Databases, record: dict) -> str:
    settings = get_settings()
    db_id = settings.appwrite_database_id

    doc = db.create_document(
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


def clear_passages(db: Databases, document_id: int) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id
    try:
        result = db.list_documents(
            database_id=db_id,
            collection_id="passages",
            queries=[Query.equal("document_id", document_id)],
        )
        for doc in result.get("documents", []):
            db.delete_document(
                database_id=db_id,
                collection_id="passages",
                document_id=doc["$id"],
            )
    except Exception:
        pass


def create_passages(db: Databases, document_id: int, passages: list[dict]) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id

    for p in passages:
        db.create_document(
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


def main() -> None:
    settings = get_settings()
    if not settings.appwrite_api_key:
        print("ERROR: APPWRITE_API_KEY not set in environment")
        sys.exit(1)

    db = get_db()
    db_id = settings.appwrite_database_id

    print(
        f"Streaming all records from {settings.dataset_name} into Appwrite DB '{db_id}'..."
    )
    print("WARNING: This will take 20-40 minutes for full dataset!")

    imported = 0
    errors = 0

    for record in stream_hf_records(limit=None, skip=0):
        doc_id = record["id"]

        for attempt in range(3):
            try:
                create_document(db, record)
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                    continue
                print(f"  ERROR creating doc {doc_id}: {e}")
                errors += 1
                break

        if errors == 0 or imported % 100 != 0:
            try:
                clear_passages(db, doc_id)
                if record["passages"]:
                    create_passages(db, doc_id, record["passages"])
            except Exception as e:
                print(f"  passages error for doc {doc_id}: {e}")

        imported += 1
        if imported % 500 == 0:
            print(f"Imported {imported} documents... (errors: {errors})")

        if imported % 1000 == 0:
            time.sleep(2)

    print(
        f"Done. Imported {imported} documents ({errors} errors) into Appwrite DB '{db_id}'."
    )


if __name__ == "__main__":
    main()

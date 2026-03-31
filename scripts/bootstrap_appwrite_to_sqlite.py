from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from appwrite.services.tables_db import TablesDB
from appwrite.client import Client
from appwrite.query import Query

from vlegal_prototype.db import (
    get_connection,
    initialize_database,
    import_documents,
)
from vlegal_prototype.hf_ingest import (
    split_into_passages,
    normalize_text,
    build_excerpt,
)


APPWRITE_ENDPOINT = "https://sgp.cloud.appwrite.io/v1"
APPWRITE_PROJECT = "69caaf1c0017a098ce99"
APPWRITE_KEY = "standard_280facd3ff0f728d3c185180323d34b591a691b8c8f05aadbb43e579b61bcef26f806f62e97bac8876dc548a5eb77543b328a9697b1d79f7eef8bf0aaeac619efef7f6231fe99dbd49b7cf6c176bc6590c94c94a421287efde7b72dced38446c3aea3f8eccfc742f6428e4e90ae67ec4b5c2df793d9707106670c63ba3882bce"
DATABASE_ID = "69caaf6900186e144449"


def get_client() -> TablesDB:
    client = Client()
    client.set_endpoint(APPWRITE_ENDPOINT)
    client.set_project(APPWRITE_PROJECT)
    client.set_key(APPWRITE_KEY)
    return TablesDB(client)


def parse_doc_from_appwrite(doc) -> dict | None:
    data = doc.data
    content = data.get("content", "") or ""
    plain = normalize_text(content)
    return {
        "id": int(doc.id),
        "document_number": data.get("document_number", "") or "",
        "title": data.get("title", None) or f"Document {doc.id}",
        "url": data.get("url", "") or "",
        "legal_type": data.get("legal_type", "") or "",
        "legal_sectors": data.get("legal_sectors", "") or "",
        "issuing_authority": data.get("issuing_authority", "") or "",
        "issuance_date": data.get("issuance_date", "") or "",
        "signers": data.get("signers", "") or "",
        "content": content,
        "plain_content": plain,
        "excerpt": build_excerpt(plain),
        "year": data.get("year"),
        "source": data.get("source", "") or "appwrite",
        "passages": split_into_passages(content),
    }


def main() -> None:
    print("Connecting to Appwrite...")
    tbdb = get_client()

    print("Fetching documents from Appwrite (limit=500)...")
    result = tbdb.list_rows(
        database_id=DATABASE_ID,
        table_id="documents",
        queries=[Query.limit(500)],
    )
    docs = result.rows
    print(f"Fetched {len(docs)} documents (total={result.total})")

    records = []
    for doc in docs:
        try:
            record = parse_doc_from_appwrite(doc)
            records.append(record)
        except Exception as e:
            print(f"  Skip doc {getattr(doc, 'id', '?')}: {e}")

    print(f"Parsed {len(records)} records. Writing to local SQLite...")

    connection = get_connection()
    initialize_database(connection)

    imported = 0
    batch = []
    for record in records:
        batch.append(record)
        if len(batch) >= 50:
            import_documents(connection, batch)
            imported += len(batch)
            print(f"Imported {imported}/{len(records)} documents...")
            batch.clear()
    if batch:
        import_documents(connection, batch)
        imported += len(batch)

    connection.close()
    print(f"Done. Imported {imported} documents into local SQLite.")
    print(f"Run: uv run uvicorn vlegal_prototype.app:app --app-dir src --reload")


if __name__ == "__main__":
    main()

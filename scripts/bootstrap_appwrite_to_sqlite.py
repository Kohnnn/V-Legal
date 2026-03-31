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
from vlegal_prototype.settings import get_settings


def get_client() -> TablesDB:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
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
    settings = get_settings()
    if (
        not settings.appwrite_project_id
        or not settings.appwrite_database_id
        or not settings.appwrite_api_key
    ):
        raise SystemExit(
            "Set VLEGAL_APPWRITE_PROJECT_ID, VLEGAL_APPWRITE_DATABASE_ID, and VLEGAL_APPWRITE_API_KEY first."
        )

    print("Connecting to Appwrite...")
    tbdb = get_client()

    print("Fetching documents from Appwrite (limit=500)...")
    result = tbdb.list_rows(
        database_id=settings.appwrite_database_id,
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

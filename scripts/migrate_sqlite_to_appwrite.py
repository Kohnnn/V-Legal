from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()

import sqlite3

from appwrite.client import Client
from appwrite.services.databases import Databases

from vlegal_prototype.settings import get_settings


def get_db() -> Databases:
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_key(settings.appwrite_api_key)
    return Databases(client)


def migrate_documents(appwrite_db: Databases, sqlite_path: str) -> None:
    settings = get_settings()
    db_id = settings.appwrite_database_id

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    print(f"Found {count} documents in SQLite")

    migrated = 0
    errors = 0

    for row in conn.execute("SELECT * FROM documents"):
        doc_data = {
            "document_number": row["document_number"] or "",
            "title": row["title"],
            "url": row["url"] or "",
            "legal_type": row["legal_type"] or "",
            "legal_sectors": row["legal_sectors"] or "",
            "issuing_authority": row["issuing_authority"] or "",
            "issuance_date": row["issuance_date"] or "",
            "signers": row["signers"] or "",
            "content": row["content"],
            "plain_content": row["plain_content"],
            "excerpt": row["excerpt"] or "",
            "year": row["year"],
            "source": row["source"],
            "imported_at": row["imported_at"],
        }

        try:
            appwrite_db.create_document(
                database_id=db_id,
                collection_id="documents",
                document_id=str(row["id"]),
                data=doc_data,
            )
            migrated += 1
        except Exception as e:
            errors += 1
            print(f"  Error doc {row['id']}: {e}")

        if migrated % 100 == 0:
            print(f"  Migrated {migrated} documents...")

    print(f"\nMigrated {migrated} documents ({errors} errors)")

    passages_migrated = 0
    passages_errors = 0
    for row in conn.execute("SELECT * FROM passages"):
        try:
            appwrite_db.create_document(
                database_id=db_id,
                collection_id="passages",
                document_id="unique()",
                data={
                    "document_id": row["document_id"],
                    "ordinal": row["ordinal"],
                    "heading": row["heading"] or "",
                    "text": row["text"],
                },
            )
            passages_migrated += 1
        except Exception as e:
            passages_errors += 1

    print(f"Migrated {passages_migrated} passages ({passages_errors} errors)")

    tracked_migrated = 0
    for row in conn.execute("SELECT * FROM tracked_documents"):
        try:
            appwrite_db.create_document(
                database_id=db_id,
                collection_id="tracked_documents",
                document_id="unique()",
                data={
                    "document_id": row["document_id"],
                    "tracked_at": row["tracked_at"],
                },
            )
            tracked_migrated += 1
        except Exception:
            pass

    print(f"Migrated {tracked_migrated} tracked documents")

    conn.close()
    print("\nSQLite migration complete!")


def main() -> None:
    settings = get_settings()
    if not settings.appwrite_api_key:
        print("ERROR: VLEGAL_APPWRITE_API_KEY not set")
        sys.exit(1)

    appwrite_db = get_db()
    sqlite_path = settings.database_path

    print(f"Migrating from SQLite: {sqlite_path}")
    print(f"To Appwrite DB: {settings.appwrite_database_id}")
    print()
    migrate_documents(appwrite_db, str(sqlite_path))


if __name__ == "__main__":
    main()

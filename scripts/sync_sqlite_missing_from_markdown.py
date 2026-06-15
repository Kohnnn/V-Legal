from __future__ import annotations

import argparse

from vlegal_prototype.corpus import (
    build_record_from_canonical_document,
    iter_canonical_documents,
)
from vlegal_prototype.db import get_connection, import_documents, initialize_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import canonical markdown documents that are still missing from the SQLite index."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many missing documents to import.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="How many missing documents to write per transaction.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connection = get_connection()
    initialize_database(connection)

    existing_canonical_ids = {
        row[0]
        for row in connection.execute(
            "SELECT canonical_id FROM documents WHERE canonical_id IS NOT NULL AND canonical_id <> ''"
        ).fetchall()
    }

    imported = 0
    missing = 0
    batch: list[dict] = []

    for document in iter_canonical_documents():
        canonical_id = str(document.metadata.get("canonical_id") or "")
        if not canonical_id or canonical_id in existing_canonical_ids:
            continue
        batch.append(build_record_from_canonical_document(document))
        missing += 1
        if args.limit and missing > args.limit:
            batch.pop()
            missing -= 1
            break
        if len(batch) < args.batch_size:
            continue
        stats = import_documents(connection, batch, skip_unchanged=False)
        imported += stats["imported_count"]
        print(f"Imported {imported} missing markdown documents...")
        batch.clear()

    if batch:
        stats = import_documents(connection, batch, skip_unchanged=False)
        imported += stats["imported_count"]

    connection.close()
    print(f"Done. Imported {imported} missing markdown documents into SQLite.")


if __name__ == "__main__":
    main()

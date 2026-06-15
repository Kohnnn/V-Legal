from __future__ import annotations

import argparse

from vlegal_prototype.corpus import (
    build_record_from_canonical_document,
    iter_canonical_documents,
)
from vlegal_prototype.db import get_connection, import_documents, initialize_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync selected canonical markdown documents into the SQLite index."
    )
    parser.add_argument(
        "--canonical-id",
        action="append",
        default=[],
        help="Canonical document ID to sync. Can be passed multiple times.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    wanted = {item for item in args.canonical_id if item}
    if not wanted:
        raise SystemExit("At least one --canonical-id is required.")

    records: list[dict] = []
    for document in iter_canonical_documents():
        canonical_id = str(document.metadata.get("canonical_id") or "")
        if canonical_id not in wanted:
            continue
        records.append(build_record_from_canonical_document(document))

    connection = get_connection()
    initialize_database(connection)
    stats = import_documents(connection, records, skip_unchanged=False)
    connection.close()
    print(
        f"Done. Received {stats['received_count']} records and imported {stats['imported_count']} into SQLite."
    )


if __name__ == "__main__":
    main()

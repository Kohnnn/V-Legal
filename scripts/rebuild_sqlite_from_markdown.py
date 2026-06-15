from __future__ import annotations

import argparse

from vlegal_prototype.citations import rebuild_citation_index
from vlegal_prototype.corpus import (
    build_record_from_canonical_document,
    iter_canonical_documents,
)
from vlegal_prototype.db import (
    get_connection,
    import_documents,
    initialize_database,
    reset_database,
)
from vlegal_prototype.relations import rebuild_relationship_graph
from vlegal_prototype.settings import get_settings
from vlegal_prototype.taxonomy import bootstrap_taxonomy


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Rebuild the local SQLite index from the canonical markdown corpus."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many markdown documents to import.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="How many records to write per transaction.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing local SQLite corpus before rebuilding.",
    )
    parser.add_argument(
        "--skip-unchanged",
        action="store_true",
        help="Skip markdown records whose source hash is unchanged.",
    )
    parser.add_argument(
        "--skip-postprocess",
        action="store_true",
        help="Skip taxonomy, relation, and citation rebuilds after importing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connection = get_connection()
    initialize_database(connection)
    if args.reset:
        print("Resetting SQLite before markdown rebuild...")
        reset_database(connection)

    documents = iter_canonical_documents(limit=args.limit or None)
    print(
        f"Rebuilding SQLite from {len(documents)} markdown documents into {get_settings().database_path}"
    )

    imported = 0
    skipped = 0
    batch: list[dict] = []
    for document in documents:
        batch.append(build_record_from_canonical_document(document))
        if len(batch) < args.batch_size:
            continue
        stats = import_documents(connection, batch, skip_unchanged=args.skip_unchanged)
        imported += stats["imported_count"]
        skipped += stats["skipped_count"]
        print(f"Imported {imported} markdown records (skipped {skipped} unchanged)...")
        batch.clear()

    if batch:
        stats = import_documents(connection, batch, skip_unchanged=args.skip_unchanged)
        imported += stats["imported_count"]
        skipped += stats["skipped_count"]

    if not args.skip_postprocess:
        print(
            "Refreshing taxonomy, relations, and citations from markdown-derived SQLite..."
        )
        bootstrap_taxonomy(connection, prefer_live=False)
        relation_count = rebuild_relationship_graph(connection)
        citation_count = rebuild_citation_index(connection)
        print(f"Built {relation_count} relations and {citation_count} citation links.")

    connection.close()
    print(f"Done. Imported {imported} markdown-derived records into SQLite.")
    if args.skip_unchanged:
        print(f"Skipped {skipped} unchanged records.")


if __name__ == "__main__":
    main()

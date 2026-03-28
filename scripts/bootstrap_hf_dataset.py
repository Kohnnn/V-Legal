from __future__ import annotations

import argparse

from vlegal_prototype.db import (
    get_connection,
    import_documents,
    initialize_database,
    reset_database,
)
from vlegal_prototype.hf_ingest import stream_hf_records
from vlegal_prototype.citations import rebuild_citation_index
from vlegal_prototype.relations import rebuild_relationship_graph
from vlegal_prototype.settings import get_settings
from vlegal_prototype.taxonomy import bootstrap_taxonomy


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Bootstrap the local V-Legal SQLite database from the HF corpus."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=settings.default_import_limit,
        help="How many documents to ingest in this run.",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="How many dataset rows to skip before importing.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="How many documents to write per transaction.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing local corpus before importing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connection = get_connection()
    initialize_database(connection)
    if args.reset:
        print("Resetting local database...")
        reset_database(connection)

    imported = 0
    batch: list[dict] = []

    print(
        f"Streaming dataset {get_settings().dataset_name} "
        f"(skip={args.skip}, limit={args.limit}, batch_size={args.batch_size})"
    )
    for record in stream_hf_records(limit=args.limit, skip=args.skip):
        batch.append(record)
        if len(batch) >= args.batch_size:
            import_documents(connection, batch)
            imported += len(batch)
            print(f"Imported {imported} documents...")
            batch.clear()

    if batch:
        import_documents(connection, batch)
        imported += len(batch)

    bootstrap_taxonomy(connection, prefer_live=False)
    relation_count = rebuild_relationship_graph(connection)
    citation_count = rebuild_citation_index(connection)
    print(f"Done. Imported {imported} documents into {get_settings().database_path}.")
    print(f"Refreshed taxonomy and built {relation_count} graph relationships.")
    print(f"Built {citation_count} explicit citation links.")
    connection.close()


if __name__ == "__main__":
    main()

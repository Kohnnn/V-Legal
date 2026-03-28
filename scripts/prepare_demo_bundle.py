from __future__ import annotations

import argparse

from vlegal_prototype.db import (
    get_connection,
    initialize_database,
    reset_database,
    import_documents,
)
from vlegal_prototype.hf_ingest import stream_hf_records
from vlegal_prototype.citations import rebuild_citation_index
from vlegal_prototype.relations import rebuild_relationship_graph
from vlegal_prototype.taxonomy import bootstrap_taxonomy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a free-tier-friendly demo bundle with a small local corpus and official taxonomy."
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--seed-only-taxonomy", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connection = get_connection()
    initialize_database(connection)
    reset_database(connection)

    imported = 0
    batch: list[dict] = []
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

    subjects = bootstrap_taxonomy(connection, prefer_live=not args.seed_only_taxonomy)
    relation_count = rebuild_relationship_graph(connection)
    citation_count = rebuild_citation_index(connection)
    connection.close()
    print(
        f"Prepared demo bundle with {imported} documents, {len(subjects)} official subjects, {relation_count} graph relationships, and {citation_count} citation links."
    )


if __name__ == "__main__":
    main()

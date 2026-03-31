from __future__ import annotations

import argparse
import json
from pathlib import Path

from vlegal_prototype.citations import rebuild_citation_index
from vlegal_prototype.db import (
    get_connection,
    import_documents,
    initialize_database,
    reset_database,
)
from vlegal_prototype.hf_ingest import stream_hf_records
from vlegal_prototype.relations import rebuild_relationship_graph
from vlegal_prototype.settings import get_settings
from vlegal_prototype.taxonomy import bootstrap_taxonomy


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Import the HF corpus in resumable chunks into local SQLite."
    )
    parser.add_argument("--chunk-size", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument(
        "--checkpoint-path",
        type=Path,
        default=settings.database_path.parent / "hf_import_checkpoint.json",
    )
    parser.add_argument("--skip-postprocess", action="store_true")
    return parser.parse_args()


def load_checkpoint(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return int(payload.get("skip", 0))


def save_checkpoint(path: Path, skip: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"skip": skip}, indent=2), encoding="utf-8")


def import_chunk(connection, skip: int, chunk_size: int, batch_size: int) -> int:
    imported = 0
    batch: list[dict] = []
    for record in stream_hf_records(limit=chunk_size, skip=skip):
        batch.append(record)
        if len(batch) >= batch_size:
            import_documents(connection, batch)
            imported += len(batch)
            print(f"  imported {imported}/{chunk_size} in current chunk...")
            batch.clear()

    if batch:
        import_documents(connection, batch)
        imported += len(batch)

    return imported


def main() -> None:
    args = parse_args()
    connection = get_connection()
    initialize_database(connection)

    if args.reset:
        print("Resetting local database before full import...")
        reset_database(connection)
        if args.checkpoint_path.exists():
            args.checkpoint_path.unlink()

    current_skip = load_checkpoint(args.checkpoint_path)
    chunks_completed = 0

    print(f"Dataset: {get_settings().dataset_name}")
    print(f"Resuming from skip={current_skip}, chunk_size={args.chunk_size}")

    while True:
        if args.max_chunks and chunks_completed >= args.max_chunks:
            break

        print(f"Starting chunk {chunks_completed + 1} at skip={current_skip}...")
        imported = import_chunk(
            connection,
            skip=current_skip,
            chunk_size=args.chunk_size,
            batch_size=args.batch_size,
        )
        current_skip += imported
        chunks_completed += 1
        save_checkpoint(args.checkpoint_path, current_skip)
        print(f"Chunk complete. Imported {imported}. Checkpoint now {current_skip}.")

        if imported < args.chunk_size:
            print("Reached end of dataset stream.")
            break

    if not args.skip_postprocess:
        print("Refreshing taxonomy, relations, and citations...")
        bootstrap_taxonomy(connection, prefer_live=False)
        relation_count = rebuild_relationship_graph(connection)
        citation_count = rebuild_citation_index(connection)
        print(f"Built {relation_count} relations and {citation_count} citation links.")

    connection.close()
    print(f"Done. Total skip checkpoint: {current_skip}")


if __name__ == "__main__":
    main()

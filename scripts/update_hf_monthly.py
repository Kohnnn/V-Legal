from __future__ import annotations

import argparse
from pathlib import Path

from bootstrap_hf_focused_corpus import (
    build_selection,
    import_selected_records,
    load_selection,
    save_selection,
)
from vlegal_prototype.citations import rebuild_citation_index
from vlegal_prototype.db import (
    finish_ingest_run,
    get_connection,
    initialize_database,
    import_documents,
    start_ingest_run,
)
from vlegal_prototype.hf_ingest import get_dataset_revision, stream_hf_records
from vlegal_prototype.relations import rebuild_relationship_graph
from vlegal_prototype.settings import get_settings
from vlegal_prototype.taxonomy import bootstrap_taxonomy


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Incrementally update the local V-Legal corpus from the monthly Hugging Face source refresh."
    )
    parser.add_argument(
        "--mode",
        choices=["focused", "full"],
        default="focused",
        help="Which corpus shape to update.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for full-corpus updates.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="How many documents to process per write transaction.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="How many focused document ids to process per cache chunk.",
    )
    parser.add_argument(
        "--selection-path",
        type=Path,
        default=settings.database_path.parent / "hf_focused_corpus_selection.json",
        help="Cached focused selection path.",
    )
    parser.add_argument(
        "--reuse-selection",
        action="store_true",
        help="Reuse the cached focused selection instead of rebuilding it.",
    )
    parser.add_argument(
        "--skip-postprocess",
        action="store_true",
        help="Skip taxonomy, relation, and citation refresh steps after importing.",
    )
    return parser.parse_args()


def update_full_corpus(
    connection, *, batch_size: int, limit: int | None
) -> dict[str, int]:
    scanned = 0
    imported = 0
    skipped = 0
    batch: list[dict] = []

    for record in stream_hf_records(limit=limit, skip=0):
        scanned += 1
        batch.append(record)
        if len(batch) < batch_size:
            continue
        stats = import_documents(connection, batch, skip_unchanged=True)
        imported += stats["imported_count"]
        skipped += stats["skipped_count"]
        print(
            f"Scanned {scanned} full-corpus records, imported {imported}, skipped {skipped} unchanged..."
        )
        batch.clear()

    if batch:
        stats = import_documents(connection, batch, skip_unchanged=True)
        imported += stats["imported_count"]
        skipped += stats["skipped_count"]

    return {
        "scanned_count": scanned,
        "imported_count": imported,
        "skipped_count": skipped,
    }


def update_focused_corpus(
    connection,
    *,
    chunk_size: int,
    batch_size: int,
    selection_path: Path,
    reuse_selection: bool,
) -> tuple[dict[str, int], int]:
    selected_ids = load_selection(selection_path) if reuse_selection else []
    if not selected_ids:
        print("Building focused selection from latest metadata...")
        selected_ids = build_selection()
        save_selection(selection_path, selected_ids)
    else:
        print(f"Loaded cached focused selection with {len(selected_ids)} document ids.")

    stats = import_selected_records(
        connection,
        selected_ids,
        chunk_size=chunk_size,
        batch_size=batch_size,
        skip_unchanged=True,
    )
    return stats, len(selected_ids)


def main() -> None:
    args = parse_args()
    settings = get_settings()
    dataset_revision = get_dataset_revision()
    connection = get_connection()
    initialize_database(connection)

    run_id = start_ingest_run(
        connection,
        dataset_name=settings.dataset_name,
        dataset_revision=dataset_revision,
        selection_mode=args.mode,
        notes="monthly updater",
    )

    scanned_count = 0
    imported_count = 0
    skipped_count = 0
    notes = ["monthly updater"]

    try:
        print(f"Dataset: {settings.dataset_name}")
        if dataset_revision:
            print(f"Dataset revision: {dataset_revision}")

        if args.mode == "focused":
            stats, selection_size = update_focused_corpus(
                connection,
                chunk_size=args.chunk_size,
                batch_size=args.batch_size,
                selection_path=args.selection_path,
                reuse_selection=args.reuse_selection,
            )
            scanned_count = stats["scanned_count"]
            imported_count = stats["imported_count"]
            skipped_count = stats["skipped_count"]
            notes.append(f"selection_size={selection_size}")
        else:
            stats = update_full_corpus(
                connection,
                batch_size=args.batch_size,
                limit=args.limit,
            )
            scanned_count = stats["scanned_count"]
            imported_count = stats["imported_count"]
            skipped_count = stats["skipped_count"]

        print(
            f"Update complete. Scanned {scanned_count}, imported {imported_count}, skipped {skipped_count} unchanged."
        )

        if not args.skip_postprocess and imported_count:
            print("Refreshing taxonomy, relations, and citations...")
            bootstrap_taxonomy(connection, prefer_live=False)
            relation_count = rebuild_relationship_graph(connection)
            citation_count = rebuild_citation_index(connection)
            notes.append(f"relations={relation_count}")
            notes.append(f"citations={citation_count}")
            print(
                f"Built {relation_count} relations and {citation_count} citation links."
            )
        elif args.skip_postprocess:
            notes.append("postprocess=skipped")
        else:
            notes.append("postprocess=unchanged")

        finish_ingest_run(
            connection,
            run_id,
            scanned_count=scanned_count,
            imported_count=imported_count,
            skipped_count=skipped_count,
            notes="; ".join(notes),
        )
    except Exception as exc:
        finish_ingest_run(
            connection,
            run_id,
            scanned_count=scanned_count,
            imported_count=imported_count,
            skipped_count=skipped_count,
            notes="; ".join([*notes, f"failed={exc}"]),
        )
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import re

from vlegal_prototype.corpus import (
    append_jsonl_record,
    emit_canonical_document,
    ensure_corpus_layout,
    load_jsonl_index,
    write_jsonl_records,
)
from vlegal_prototype.hf_ingest import iter_hf_parquet_batches, prepare_parquet_metadata_only_record
from vlegal_prototype.settings import get_settings


HF_FILENAME_PATTERN = re.compile(r"^vn-issued-hf-(\d+)--")


def existing_hf_markdown_ids() -> set[int]:
    paths = ensure_corpus_layout()
    ids: set[int] = set()
    for file_path in paths.markdown_root.rglob("vn-issued-hf-*.md"):
        match = HF_FILENAME_PATTERN.match(file_path.name)
        if not match:
            continue
        ids.add(int(match.group(1)))
    return ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export metadata-only HF documents that are missing from the canonical markdown corpus."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many metadata-only docs to export.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ensure_corpus_layout()
    manifest_index = load_jsonl_index(paths.documents_manifest)
    existing_ids = existing_hf_markdown_ids()

    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "hf_metadata_only_export_started",
            "dataset_name": get_settings().dataset_name,
            "existing_hf_markdown_count": len(existing_ids),
        },
    )

    exported = 0
    for batch in iter_hf_parquet_batches("data/metadata.parquet", batch_size=256):
        for metadata in batch:
            document_id = int(metadata["id"])
            if document_id in existing_ids:
                continue
            record = prepare_parquet_metadata_only_record(metadata)
            manifest_entry = emit_canonical_document(
                {
                    **record,
                    "text_source": "metadata",
                    "document_layer": "issued",
                },
                source_system="hf_bootstrap",
                source_document_id=document_id,
                raw_snapshot=str(metadata),
                raw_snapshot_extension=".txt",
                source_url="",
                document_layer="issued",
                trust_level="bootstrap_only",
            )
            manifest_index[manifest_entry["canonical_id"]] = manifest_entry
            existing_ids.add(document_id)
            exported += 1
            if exported % 100 == 0:
                print(f"Exported {exported} metadata-only HF markdown documents...")
            if args.limit and exported >= args.limit:
                break
        if args.limit and exported >= args.limit:
            break

    write_jsonl_records(
        paths.documents_manifest,
        sorted(manifest_index.values(), key=lambda item: item["canonical_id"]),
    )
    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "hf_metadata_only_export_finished",
            "dataset_name": get_settings().dataset_name,
            "exported_count": exported,
        },
    )
    print(f"Done. Exported {exported} metadata-only HF markdown documents.")


if __name__ == "__main__":
    main()

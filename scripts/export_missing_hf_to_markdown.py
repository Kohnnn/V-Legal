from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from vlegal_prototype.corpus import (
    append_jsonl_record,
    emit_canonical_document,
    ensure_corpus_layout,
    load_jsonl_index,
    write_jsonl_records,
)
from vlegal_prototype.hf_ingest import stream_hf_source_records_by_ids
from vlegal_prototype.settings import BASE_DIR, get_settings


HF_CACHE_PATH = BASE_DIR / "data" / "hf_content_cache.sqlite"
HF_FILENAME_PATTERN = re.compile(r"^vn-issued-hf-(\d+)--")


def compute_missing_hf_ids() -> list[int]:
    connection = sqlite3.connect(HF_CACHE_PATH)
    source_ids = {
        int(row[0]) for row in connection.execute("SELECT id FROM content_cache")
    }
    connection.close()

    paths = ensure_corpus_layout()
    exported_ids: set[int] = set()
    for file_path in paths.markdown_root.rglob("vn-issued-hf-*.md"):
        match = HF_FILENAME_PATTERN.match(file_path.name)
        if not match:
            continue
        exported_ids.add(int(match.group(1)))
    return sorted(source_ids - exported_ids)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the exact HF source IDs that are still missing from the canonical markdown corpus."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many missing HF IDs to export.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ensure_corpus_layout()
    manifest_index = load_jsonl_index(paths.documents_manifest)
    missing_ids = compute_missing_hf_ids()
    if args.limit:
        missing_ids = missing_ids[: args.limit]

    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "hf_missing_markdown_export_started",
            "dataset_name": get_settings().dataset_name,
            "missing_id_count": len(missing_ids),
        },
    )

    exported = 0
    for item in stream_hf_source_records_by_ids(missing_ids):
        record = dict(item["record"])
        content_payload = item.get("content") or {}
        raw_snapshot = (
            content_payload.get("content_html") or content_payload.get("content") or ""
        )
        raw_extension = ".html" if content_payload.get("content_html") else ".txt"
        manifest_entry = emit_canonical_document(
            {
                **record,
                "text_source": "html"
                if content_payload.get("content_html")
                else "text",
                "document_layer": "issued",
            },
            source_system="hf_bootstrap",
            source_document_id=record["id"],
            raw_snapshot=raw_snapshot,
            raw_snapshot_extension=raw_extension,
            source_url=record.get("url") or "",
            document_layer="issued",
            trust_level="bootstrap_only",
        )
        manifest_index[manifest_entry["canonical_id"]] = manifest_entry
        exported += 1
        if exported % 100 == 0:
            print(f"Exported {exported} missing HF markdown documents...")

    write_jsonl_records(
        paths.documents_manifest,
        sorted(manifest_index.values(), key=lambda item: item["canonical_id"]),
    )
    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "hf_missing_markdown_export_finished",
            "dataset_name": get_settings().dataset_name,
            "missing_id_count": len(missing_ids),
            "exported_count": exported,
        },
    )
    print(f"Done. Exported {exported} missing HF markdown documents.")


if __name__ == "__main__":
    main()

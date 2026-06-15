from __future__ import annotations

import argparse

from vlegal_prototype.corpus import (
    append_jsonl_record,
    emit_canonical_document,
    ensure_corpus_layout,
    load_jsonl_index,
    reset_corpus_layout,
    write_jsonl_records,
)
from vlegal_prototype.hf_ingest import stream_hf_source_records
from vlegal_prototype.hf_ingest import stream_hf_source_records_by_ids
from vlegal_prototype.settings import get_settings


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Export the HF corpus into the local canonical markdown corpus."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=settings.default_import_limit,
        help="How many documents to export in this run.",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="How many source records to skip before exporting.",
    )
    parser.add_argument(
        "--document-id",
        action="append",
        type=int,
        default=[],
        help="Specific HF source document ID to export. Can be passed multiple times.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the markdown corpus before exporting.",
    )
    parser.add_argument(
        "--trust-level",
        default="bootstrap_only",
        help="Trust level to assign to emitted documents.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = reset_corpus_layout() if args.reset else ensure_corpus_layout()
    manifest_index = {} if args.reset else load_jsonl_index(paths.documents_manifest)

    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "hf_markdown_export_started",
            "dataset_name": get_settings().dataset_name,
            "limit": args.limit,
            "skip": args.skip,
            "document_ids": args.document_id,
            "trust_level": args.trust_level,
        },
    )

    exported = 0
    source_iter = (
        stream_hf_source_records_by_ids(args.document_id)
        if args.document_id
        else stream_hf_source_records(limit=args.limit, skip=args.skip)
    )
    for item in source_iter:
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
            trust_level=args.trust_level,
        )
        manifest_index[manifest_entry["canonical_id"]] = manifest_entry
        exported += 1
        if exported % 100 == 0:
            print(f"Exported {exported} canonical markdown documents...")

    write_jsonl_records(
        paths.documents_manifest,
        sorted(manifest_index.values(), key=lambda item: item["canonical_id"]),
    )
    append_jsonl_record(
        paths.source_runs_manifest,
        {
            "kind": "hf_markdown_export_finished",
            "dataset_name": get_settings().dataset_name,
            "limit": args.limit,
            "skip": args.skip,
            "document_ids": args.document_id,
            "trust_level": args.trust_level,
            "exported_count": exported,
        },
    )
    print(f"Done. Exported {exported} markdown documents under {paths.root}.")


if __name__ == "__main__":
    main()

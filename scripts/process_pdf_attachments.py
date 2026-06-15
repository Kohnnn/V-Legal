from __future__ import annotations

import argparse
import json

from pathlib import Path

from vlegal_prototype.corpus import (
    CanonicalDocument,
    append_jsonl_record,
    build_record_from_canonical_document,
    ensure_corpus_layout,
    load_jsonl_index,
    split_frontmatter,
)
from vlegal_prototype.db import get_connection, import_documents, initialize_database
from vlegal_prototype.minimax_text import (
    correct_ocr_text_with_minimax,
    has_minimax_credentials,
)
from vlegal_prototype.pdf_ocr import (
    iter_pdf_ocr_targets,
    process_pdf_attachment_for_document,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download PDF attachments, extract text, and write structured markdown back into canonical corpus records."
    )
    parser.add_argument(
        "--canonical-id",
        action="append",
        default=[],
        help="Specific canonical ID to process. Can be repeated.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="How many queued PDF-backed records to process when canonical IDs are not provided.",
    )
    parser.add_argument(
        "--backend",
        default="auto",
        help="PDF extraction backend. Default is auto.",
    )
    parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Include records that already have medium or high OCR output when no canonical IDs are provided.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="HTTP timeout in seconds for downloading attachments.",
    )
    parser.add_argument(
        "--max-ocr-pages",
        type=int,
        default=0,
        help="Optional maximum number of leading pages to OCR for scan-heavy PDFs.",
    )
    parser.add_argument(
        "--auto-minimax",
        action="store_true",
        help="Automatically run MiniMax post-correction after OCR when credentials are configured.",
    )
    parser.add_argument(
        "--minimax-mode",
        default="recommended",
        choices=["recommended", "optional", "all"],
        help="Which OCR LLM recommendations should trigger automatic MiniMax correction.",
    )
    parser.add_argument(
        "--sync-sqlite",
        action="store_true",
        help="Import successfully updated markdown documents into the active SQLite database.",
    )
    return parser.parse_args()


def load_canonical_record(canonical_id: str) -> dict:
    paths = ensure_corpus_layout()
    manifest_entry = load_jsonl_index(paths.documents_manifest).get(canonical_id)
    if manifest_entry is None:
        raise ValueError(f"Unknown canonical_id in manifest: {canonical_id}")
    markdown_path = paths.root / Path(str(manifest_entry.get("markdown_path") or ""))
    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown path does not exist: {markdown_path}")
    metadata, body = split_frontmatter(markdown_path.read_text(encoding="utf-8"))
    return build_record_from_canonical_document(
        CanonicalDocument(file_path=markdown_path, metadata=metadata, body=body)
    )


def main() -> None:
    args = parse_args()
    paths = ensure_corpus_layout()
    canonical_ids = list(args.canonical_id)
    if not canonical_ids:
        targets = iter_pdf_ocr_targets(
            limit=args.limit or None,
            include_completed=args.include_completed,
        )
        canonical_ids = [target.canonical_id for target in targets]

    processed = 0
    updated_ids: list[str] = []
    failures: list[dict[str, str]] = []
    minimax_available = has_minimax_credentials()
    for canonical_id in canonical_ids:
        try:
            result = process_pdf_attachment_for_document(
                canonical_id=canonical_id,
                backend=args.backend,
                timeout=args.timeout,
                max_ocr_pages=args.max_ocr_pages or None,
            )
            processed += 1
            updated_ids.append(result["canonical_id"])
            append_jsonl_record(
                paths.manifests_root / "pdf_ocr_runs.jsonl",
                {
                    "canonical_id": result["canonical_id"],
                    "backend": result["backend"],
                    "text_source": result.get("text_source") or "",
                    "parse_confidence": result["parse_confidence"],
                    "ocr_llm_recommendation": result.get("ocr_llm_assessment", {}).get(
                        "recommendation", ""
                    ),
                    "status": "processed",
                },
            )

            llm_recommendation = result.get("ocr_llm_assessment", {}).get(
                "recommendation", ""
            )
            should_run_minimax = False
            if args.auto_minimax and minimax_available:
                if args.minimax_mode == "all" and llm_recommendation:
                    should_run_minimax = True
                elif args.minimax_mode == "optional" and llm_recommendation in {
                    "optional",
                    "recommended",
                }:
                    should_run_minimax = True
                elif (
                    args.minimax_mode == "recommended"
                    and llm_recommendation == "recommended"
                ):
                    should_run_minimax = True

            if should_run_minimax:
                minimax_result = correct_ocr_text_with_minimax(result["canonical_id"])
                updated_ids.append(minimax_result["canonical_id"])
                append_jsonl_record(
                    paths.manifests_root / "pdf_ocr_runs.jsonl",
                    {
                        "canonical_id": minimax_result["canonical_id"],
                        "backend": "minimax_text_correction",
                        "status": "corrected",
                        "pre_recommendation": minimax_result.get(
                            "pre_assessment", {}
                        ).get("recommendation", ""),
                        "post_recommendation": minimax_result.get(
                            "post_assessment", {}
                        ).get("recommendation", ""),
                    },
                )
                print(
                    f"MiniMax corrected {minimax_result['canonical_id']} "
                    f"({minimax_result.get('pre_assessment', {}).get('recommendation', 'unknown')} -> "
                    f"{minimax_result.get('post_assessment', {}).get('recommendation', 'unknown')})."
                )

            print(
                f"Processed {result['canonical_id']} via {result['backend']} with {result['parse_confidence']} confidence; "
                f"OCR LLM: {result.get('ocr_llm_assessment', {}).get('recommendation', 'unknown')}."
            )
        except Exception as exc:
            failures.append({"canonical_id": canonical_id, "error": str(exc)})
            append_jsonl_record(
                paths.manifests_root / "pdf_ocr_runs.jsonl",
                {
                    "canonical_id": canonical_id,
                    "backend": args.backend,
                    "status": "failed",
                    "error": str(exc),
                },
            )
            print(f"Failed {canonical_id}: {exc}")
    if args.sync_sqlite and updated_ids:
        records = [load_canonical_record(canonical_id) for canonical_id in sorted(set(updated_ids))]
        connection = get_connection()
        initialize_database(connection)
        stats = import_documents(connection, records, skip_unchanged=False)
        connection.close()
        print(
            f"Synced {stats['imported_count']} OCR-updated documents into SQLite."
        )
    print(f"Done. Processed {processed} PDF-backed corpus records.")
    if failures:
        print(json.dumps(failures, ensure_ascii=False))


if __name__ == "__main__":
    main()

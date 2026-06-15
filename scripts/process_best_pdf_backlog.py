from __future__ import annotations

import argparse
import json

import fitz

from vlegal_prototype.corpus import (
    append_jsonl_record,
    build_record_from_canonical_document,
    ensure_corpus_layout,
    iter_canonical_documents,
    split_frontmatter,
)
from vlegal_prototype.db import get_connection, import_documents, initialize_database
from vlegal_prototype.pdf_ocr import download_pdf_attachment, process_pdf_attachment_for_document


def load_processed_ids(runs_path) -> set[str]:
    seen: set[str] = set()
    if not runs_path.exists():
        return seen
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("status") in {"processed", "failed", "corrected"}:
            canonical_id = str(item.get("canonical_id") or "")
            if canonical_id:
                seen.add(canonical_id)
    return seen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process the highest-yield PDF backlog documents first and sync them into SQLite."
    )
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=120,
        help="How many fresh backlog documents to score before selecting the best ones.",
    )
    parser.add_argument(
        "--sample-pages",
        type=int,
        default=3,
        help="How many leading pages to sample for text yield scoring.",
    )
    parser.add_argument(
        "--min-sample-text-len",
        type=int,
        default=500,
        help="Minimum direct-extraction text length across sampled pages to qualify.",
    )
    parser.add_argument(
        "--process-limit",
        type=int,
        default=5,
        help="How many top-ranked documents to process.",
    )
    parser.add_argument(
        "--backend",
        default="auto",
        help="Backend to use when processing selected documents.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Attachment/OCR timeout in seconds per document.",
    )
    parser.add_argument(
        "--download-timeout",
        type=int,
        default=45,
        help="Timeout in seconds while downloading candidate PDFs for scoring.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ensure_corpus_layout()
    runs_path = paths.manifests_root / "pdf_ocr_runs.jsonl"
    processed_ids = load_processed_ids(runs_path)
    candidates: list[dict] = []
    scanned = 0

    with paths.documents_manifest.open(encoding="utf-8") as handle:
        manifest_entries = [
            json.loads(line)
            for line in handle
            if line.strip()
        ]

    for metadata in manifest_entries:
        canonical_id = str(metadata.get("canonical_id") or "")
        if not canonical_id.startswith("vn-issued-vpcp-"):
            continue
        if canonical_id in processed_ids:
            continue
        if str(metadata.get("text_source") or "") != "pdf":
            continue
        if str(metadata.get("parse_confidence") or "").lower() != "low":
            continue

        markdown_path = paths.root / str(metadata.get("markdown_path") or "")
        if not markdown_path.exists():
            continue
        document_metadata, _ = split_frontmatter(
            markdown_path.read_text(encoding="utf-8")
        )

        attachments = [
            item
            for item in document_metadata.get("attachments") or []
            if str(item).lower().endswith(".pdf")
        ]
        if not attachments:
            continue

        scanned += 1
        try:
            pdf_path = download_pdf_attachment(
                canonical_id=canonical_id,
                attachment_url=str(attachments[0]),
                timeout=args.download_timeout,
            )
            document_pdf = fitz.open(pdf_path)
            sample_text = "".join(
                (page.get_text("text") or "")
                for page in document_pdf[: args.sample_pages]
            )
            page_count = len(document_pdf)
            candidates.append(
                {
                    "canonical_id": canonical_id,
                    "document_number": str(metadata.get("document_number") or ""),
                    "pages": page_count,
                    "sample_text_len": len(sample_text),
                }
            )
            document_pdf.close()
            print(
                f"Scored {canonical_id}: {len(sample_text)} chars across {page_count} pages.",
                flush=True,
            )
        except Exception as exc:
            print(f"Skipped {canonical_id}: {exc}", flush=True)
            continue
        if scanned >= args.scan_limit:
            break

    candidates = [
        item for item in candidates if item["sample_text_len"] >= args.min_sample_text_len
    ]
    candidates.sort(key=lambda item: (-item["sample_text_len"], item["pages"]))
    selected = candidates[: args.process_limit]

    print(json.dumps({"selected": selected}, ensure_ascii=False), flush=True)

    synced_ids: list[str] = []
    for item in selected:
        result = process_pdf_attachment_for_document(
            canonical_id=item["canonical_id"],
            backend=args.backend,
            timeout=args.timeout,
        )
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
        synced_ids.append(result["canonical_id"])
        print(
            f"Processed {result['canonical_id']} via {result['backend']} with {result['parse_confidence']} confidence."
        )

    if not synced_ids:
        print("Done. No qualifying backlog documents found.")
        return

    records: list[dict] = []
    wanted = set(synced_ids)
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
        f"Done. Processed {len(synced_ids)} documents and imported {stats['imported_count']} into SQLite."
    )


if __name__ == "__main__":
    main()

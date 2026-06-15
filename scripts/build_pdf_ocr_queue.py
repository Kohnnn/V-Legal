from __future__ import annotations

import argparse
import json

from vlegal_prototype.corpus import ensure_corpus_layout, write_jsonl_records
from vlegal_prototype.pdf_ocr import build_pdf_ocr_queue, detect_pdf_ocr_capabilities


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a PDF OCR work queue for canonical markdown documents with PDF-backed content."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on queue size.",
    )
    parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Include documents that already have medium or high OCR output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ensure_corpus_layout()
    queue = build_pdf_ocr_queue(
        limit=args.limit or None,
        include_completed=args.include_completed,
    )
    queue_path = paths.manifests_root / "pdf_ocr_queue.jsonl"
    write_jsonl_records(queue_path, queue)
    capabilities = [
        {
            "name": item.name,
            "available": item.available,
            "kind": item.kind,
            "notes": item.notes,
        }
        for item in detect_pdf_ocr_capabilities()
    ]
    capabilities_path = paths.manifests_root / "pdf_ocr_capabilities.json"
    capabilities_path.write_text(
        json.dumps(capabilities, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Queued {len(queue)} PDF OCR targets in {queue_path}")
    print(f"Wrote capability report to {capabilities_path}")


if __name__ == "__main__":
    main()

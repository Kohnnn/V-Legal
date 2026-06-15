from __future__ import annotations

import argparse
from pathlib import Path

from vlegal_prototype.pdf_ocr import apply_ocr_text_to_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply OCR text to a canonical markdown document using deterministic structure mapping."
    )
    parser.add_argument("--canonical-id", required=True, help="Canonical document ID.")
    parser.add_argument("--text-file", required=True, help="OCR text file path.")
    parser.add_argument(
        "--backend",
        required=True,
        help="Name of the OCR backend that produced the text, such as paddleocr_ppstructure or vietocr.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_text = Path(args.text_file).read_text(encoding="utf-8")
    result = apply_ocr_text_to_document(
        canonical_id=args.canonical_id,
        raw_text=raw_text,
        backend=args.backend,
    )
    print(
        f"Updated {result['canonical_id']} with OCR text via {result['backend']}. "
        f"Raw OCR saved to {result['raw_text_path']}"
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse

from vlegal_prototype.minimax_text import correct_ocr_text_with_minimax


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MiniMax text-only post-correction on an OCR-backed legal document."
    )
    parser.add_argument("--canonical-id", required=True, help="Canonical document ID.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = correct_ocr_text_with_minimax(args.canonical_id)
    print(
        f"Applied MiniMax OCR correction to {result['canonical_id']}. "
        f"Output: {result['corrected_text_path']}"
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vlegal_prototype.pdf_ocr import map_ocr_text_to_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview how OCR text would map into the legal markdown schema."
    )
    parser.add_argument("--text-file", required=True, help="Path to OCR text input.")
    parser.add_argument("--title", default="", help="Optional document title.")
    parser.add_argument(
        "--output-file",
        default="",
        help="Optional output markdown file. If omitted, prints to stdout.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8")
    markdown = map_ocr_text_to_markdown(text, title=args.title)
    if args.output_file:
        Path(args.output_file).write_text(markdown, encoding="utf-8")
        print(f"Wrote markdown preview to {args.output_file}")
        return
    sys.stdout.write(markdown)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from vlegal_prototype.corpus import ensure_corpus_layout
from vlegal_prototype.settings import BASE_DIR


HF_FILENAME_PATTERN = re.compile(r"^vn-issued-hf-(\d+)--")
HF_CACHE_PATH = BASE_DIR / "data" / "hf_content_cache.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print HF source IDs that exist in the local content cache but are still missing from the canonical markdown corpus."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many missing IDs to print.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = ensure_corpus_layout()

    connection = sqlite3.connect(HF_CACHE_PATH)
    source_ids = {
        str(row[0]) for row in connection.execute("SELECT id FROM content_cache")
    }
    connection.close()

    exported_ids: set[str] = set()
    for file_path in paths.markdown_root.rglob("vn-issued-hf-*.md"):
        match = HF_FILENAME_PATTERN.match(file_path.name)
        if match:
            exported_ids.add(match.group(1))

    missing_ids = sorted(source_ids - exported_ids, key=int)
    if args.limit:
        missing_ids = missing_ids[: args.limit]
    for item in missing_ids:
        print(item)


if __name__ == "__main__":
    main()

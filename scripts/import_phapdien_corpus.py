from __future__ import annotations

import argparse

from vlegal_prototype.phapdien import import_phapdien_corpus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import the official Phap dien ebook bundle into the local markdown corpus."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many đề mục files to emit.",
    )
    parser.add_argument(
        "--topic-id",
        action="append",
        default=[],
        help="Specific đề mục UUID to import. Can be passed multiple times.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="HTTP timeout in seconds for downloading the ebook zip.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = import_phapdien_corpus(
        limit=args.limit or None,
        topic_ids={item.lower() for item in args.topic_id} or None,
        timeout=args.timeout,
    )
    print(
        "Imported "
        f"{stats['exported_count']} phap dien topic markdown files "
        f"from {stats['subjects_count']} subjects, {stats['topics_count']} topics, "
        f"and {stats['tree_nodes_count']} tree nodes."
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse

from vlegal_prototype.vbpl import backfill_official_vbpl_links_into_issued_corpus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Harvest official VBPL links from imported Phap dien topics and backfill them into issued markdown files."
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing official VBPL metadata on issued markdown files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = backfill_official_vbpl_links_into_issued_corpus(
        overwrite=args.overwrite,
    )
    print(
        f"Harvested {stats['reference_document_count']} VBPL reference documents; "
        f"matched {stats['candidate_match_count']} issued markdown files; "
        f"updated {stats['updated_count']} files."
    )


if __name__ == "__main__":
    main()

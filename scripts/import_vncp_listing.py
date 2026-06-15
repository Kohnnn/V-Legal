from __future__ import annotations

import argparse

from vlegal_prototype.vncp import import_government_listing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import issued documents from the Government Portal legal-document listing into the local markdown corpus."
    )
    parser.add_argument(
        "--typegroupid",
        type=int,
        default=3,
        help="Government Portal legal-document type group to crawl. Default is 3 (Luật - Pháp lệnh).",
    )
    parser.add_argument(
        "--orggroupid",
        type=int,
        default=0,
        help="Optional issuing-authority group filter.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="How many listing rows to import from the current listing page.",
    )
    parser.add_argument(
        "--maxresults",
        type=int,
        default=50,
        help="Requested server-side listing size. The portal often renders 50 by default.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--no-backfill-existing",
        action="store_true",
        help="Do not backfill matching issued markdown files with official Government Portal provenance.",
    )
    parser.add_argument(
        "--overwrite-backfill",
        action="store_true",
        help="Overwrite existing official-source metadata during backfill.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    orggroupid = args.orggroupid if args.orggroupid else None
    stats = import_government_listing(
        typegroupid=args.typegroupid,
        orggroupid=orggroupid,
        limit=args.limit or None,
        maxresults=args.maxresults,
        timeout=args.timeout,
        backfill_existing=not args.no_backfill_existing,
        overwrite_backfill=args.overwrite_backfill,
    )
    print(
        f"Imported {stats['imported_count']} Government Portal records; "
        f"scanned {stats['listing_row_count']} listing rows; "
        f"backfill updated {stats['backfill_updated_count']} existing issued files."
    )


if __name__ == "__main__":
    main()

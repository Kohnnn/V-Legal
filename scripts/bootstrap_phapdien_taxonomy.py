from __future__ import annotations

import argparse

from vlegal_prototype.db import get_connection, initialize_database
from vlegal_prototype.taxonomy import bootstrap_taxonomy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load the official Phap dien subject taxonomy into the local database."
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Use the checked-in official subject seed instead of attempting a live refresh.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connection = get_connection()
    initialize_database(connection)
    subjects = bootstrap_taxonomy(connection, prefer_live=not args.seed_only)
    print(
        f"Loaded {len(subjects)} official Phap dien subjects into the local database."
    )
    connection.close()


if __name__ == "__main__":
    main()

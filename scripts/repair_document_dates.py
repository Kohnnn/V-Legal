from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vlegal_prototype.hf_ingest import get_max_reasonable_year, normalize_issuance_date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair implausible document issuance years in SQLite."
    )
    parser.add_argument("database_path", help="Path to the SQLite database file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    connection = sqlite3.connect(args.database_path)
    connection.row_factory = sqlite3.Row

    rows = connection.execute(
        """
        SELECT id, document_number, title, issuance_date, year
        FROM documents
        WHERE COALESCE(issuance_date, '') <> ''
           OR year IS NOT NULL
        ORDER BY id ASC
        """
    ).fetchall()

    repaired = 0
    with connection:
        for row in rows:
            issuance_date, year = normalize_issuance_date(
                row["issuance_date"], row["document_number"], row["title"]
            )
            if issuance_date == (row["issuance_date"] or "") and year == row["year"]:
                continue

            connection.execute(
                "UPDATE documents SET issuance_date = ?, year = ? WHERE id = ?",
                (issuance_date, year, row["id"]),
            )
            repaired += 1

    print(f"Repaired {repaired} document date rows.")
    max_reasonable_year = get_max_reasonable_year()
    years = connection.execute(
        "SELECT MIN(year), MAX(year) FROM documents WHERE year BETWEEN 1800 AND ?",
        (max_reasonable_year,),
    ).fetchone()
    print(f"Sane year range: {years[0]} - {years[1]}")
    connection.close()


if __name__ == "__main__":
    main()

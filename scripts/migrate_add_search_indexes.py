"""Backfill search indexes onto an existing V-Legal SQLite database.

This migration is additive and idempotent. It:

1. adds the ``document_number_norm`` column if missing,
2. backfills it from ``document_number`` using the same normalization the
   importer uses,
3. creates the supporting search indexes
   (``idx_documents_document_number_norm``, ``idx_documents_issuing_authority``,
   ``idx_documents_imported_at``),
4. runs ``ANALYZE`` so the query planner has fresh statistics.

It operates ONLY on the database pointed to by ``VLEGAL_DATABASE_PATH``
(default: the workspace corpus DB at ``data/corpus/sqlite/vlegal.sqlite``).
It never touches deploy/OCI configuration.

IMPORTANT: stop the local dev server first. A concurrent reader (e.g. uvicorn
on :8000) blocks WAL checkpoints, so the WAL grows unbounded on top of the
multi-GB database and the backfill slows to a crawl. With the server stopped,
the backfill drops the heavy ``documents_au`` FTS trigger for the duration so
updating a non-FTS column does not re-tokenize every row.

Usage:
    uv run python scripts/migrate_add_search_indexes.py
    uv run python scripts/migrate_add_search_indexes.py --batch-size 20000
    uv run python scripts/migrate_add_search_indexes.py --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import time

from vlegal_prototype.db import normalize_document_number
from vlegal_prototype.settings import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill document_number_norm and search indexes on the workspace DB."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20000,
        help="Rows updated per commit during backfill.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    return parser.parse_args()


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def main() -> None:
    args = parse_args()
    settings = get_settings()
    db_path = settings.database_path
    print(f"Target database: {db_path}")

    connection = sqlite3.connect(db_path, timeout=60.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 60000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")

    try:
        has_column = _column_exists(connection, "documents", "document_number_norm")
        print(f"document_number_norm column present: {has_column}")
        if not has_column:
            if args.dry_run:
                print("[dry-run] would ADD COLUMN document_number_norm")
            else:
                connection.execute(
                    "ALTER TABLE documents ADD COLUMN document_number_norm TEXT"
                )
                connection.commit()
                print("Added column document_number_norm")
                has_column = True

        total = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        if has_column:
            pending = connection.execute(
                """
                SELECT COUNT(*)
                FROM documents
                WHERE document_number_norm IS NULL
                  AND COALESCE(document_number, '') != ''
                """
            ).fetchone()[0]
        else:
            # Dry-run before the column exists: every numbered row would backfill.
            pending = connection.execute(
                "SELECT COUNT(*) FROM documents WHERE COALESCE(document_number, '') != ''"
            ).fetchone()[0]
        print(f"Documents: {total:,}; rows needing backfill: {pending:,}")

        if args.dry_run:
            print("[dry-run] would backfill, create indexes, and ANALYZE.")
            return

        # The legacy ``documents_au`` trigger reindexes FTS on EVERY update, so
        # backfilling a non-FTS column would re-tokenize title/plain_content for
        # all 150k rows (~50s per 2k rows). Drop it during the backfill and
        # recreate the guarded version (only fires when FTS columns change)
        # afterwards. document_number_norm is not part of any FTS index, so this
        # is safe.
        print("Dropping legacy documents_au FTS trigger during backfill ...")
        connection.execute("DROP TRIGGER IF EXISTS documents_au")
        connection.commit()

        updated = 0
        started = time.time()
        while True:
            rows = connection.execute(
                """
                SELECT id, document_number
                FROM documents
                WHERE document_number_norm IS NULL
                  AND COALESCE(document_number, '') != ''
                LIMIT ?
                """,
                (args.batch_size,),
            ).fetchall()
            if not rows:
                break
            payload = [
                (normalize_document_number(row["document_number"]), row["id"])
                for row in rows
            ]
            connection.executemany(
                "UPDATE documents SET document_number_norm = ? WHERE id = ?",
                payload,
            )
            connection.commit()
            updated += len(payload)
            print(f"  backfilled {updated:,}/{pending:,}", flush=True)
            # Keep the WAL bounded. Only effective when no other connection holds
            # a read lock, so stop the local dev server before running this.
            connection.execute("PRAGMA wal_checkpoint(PASSIVE)")

        # Also normalize rows where the stored norm is empty string but a number
        # exists (e.g. from a partial earlier run).
        connection.execute(
            """
            UPDATE documents
            SET document_number_norm = ''
            WHERE document_number_norm IS NULL
              AND COALESCE(document_number, '') = ''
            """
        )
        connection.commit()

        print("Recreating guarded documents_au FTS trigger ...")
        connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents
            WHEN old.title IS NOT new.title
                OR old.plain_content IS NOT new.plain_content
                OR old.excerpt IS NOT new.excerpt
            BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, plain_content, excerpt)
                VALUES ('delete', old.id, old.title, old.plain_content, old.excerpt);
                INSERT INTO documents_fts(rowid, title, plain_content, excerpt)
                VALUES (new.id, new.title, new.plain_content, new.excerpt);
            END
            """
        )
        connection.commit()

        print("Creating indexes (idempotent) ...")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_document_number_norm "
            "ON documents(document_number_norm)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_issuing_authority "
            "ON documents(issuing_authority)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_imported_at "
            "ON documents(imported_at DESC, id DESC)"
        )
        connection.commit()

        print("Running ANALYZE ...")
        connection.execute("ANALYZE")
        connection.commit()

        elapsed = time.time() - started
        print(f"Done. Backfilled {updated:,} rows in {elapsed:.1f}s.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
